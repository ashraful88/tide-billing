"""Dunning escalation and the order-to-invoice flow."""

from datetime import timedelta
from decimal import Decimal

from django.core import mail
from django.urls import reverse
from django.utils import timezone

from invoices.models import Invoice, InvoiceStatus
from invoices.tasks import (
    DUNNING_SCHEDULE_DAYS,
    mark_overdue_invoices,
    send_invoice_email,
    send_invoice_reminders,
)
from tidebilling import factories
from tidebilling.apitest import AuthenticatedAPITestCase


def _overdue_invoice(days, **kwargs):
    kwargs.setdefault('status', InvoiceStatus.SENT)
    kwargs.setdefault('total_amount', Decimal('100.00'))
    invoice = factories.make_invoice(
        due_date=timezone.localdate() - timedelta(days=days), **kwargs
    )
    invoice.outstanding_amount = invoice.total_amount
    invoice.save()
    return invoice


class DunningEscalationTests(AuthenticatedAPITestCase):
    def test_first_reminder_goes_out_immediately_after_due_date(self):
        invoice = _overdue_invoice(1)

        sent = send_invoice_reminders()

        invoice.refresh_from_db()
        self.assertEqual(sent, 1)
        self.assertEqual(invoice.reminder_count, 1)
        self.assertEqual(invoice.status, InvoiceStatus.OVERDUE)
        self.assertIsNotNone(invoice.last_reminder_at)

    def test_reminders_escalate_rather_than_firing_once(self):
        """The old filter excluded OVERDUE, capping every invoice at one email."""
        invoice = _overdue_invoice(1)
        send_invoice_reminders()
        self.assertEqual(len(mail.outbox), 1)

        # Still day 1: the next step is not due yet.
        send_invoice_reminders()
        self.assertEqual(len(mail.outbox), 1)

        # Day 8 crosses the second threshold.
        invoice.refresh_from_db()
        invoice.due_date = timezone.localdate() - timedelta(days=8)
        invoice.save()
        send_invoice_reminders()

        invoice.refresh_from_db()
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(invoice.reminder_count, 2)

    def test_escalation_stops_after_the_last_step(self):
        invoice = _overdue_invoice(365)
        invoice.reminder_count = len(DUNNING_SCHEDULE_DAYS)
        invoice.save()

        sent = send_invoice_reminders()

        self.assertEqual(sent, 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_reminder_subject_shows_the_escalation_step(self):
        _overdue_invoice(1)

        send_invoice_reminders()

        self.assertIn(
            f'1/{len(DUNNING_SCHEDULE_DAYS)}', mail.outbox[0].subject
        )

    def test_partially_paid_invoices_are_chased(self):
        _overdue_invoice(1, status=InvoiceStatus.PARTIALLY_PAID)

        self.assertEqual(send_invoice_reminders(), 1)

    def test_paid_and_draft_invoices_are_not_chased(self):
        _overdue_invoice(10, status=InvoiceStatus.PAID)
        _overdue_invoice(10, status=InvoiceStatus.DRAFT)

        self.assertEqual(send_invoice_reminders(), 0)

    def test_invoices_not_yet_due_are_not_chased(self):
        factories.make_invoice(
            due_date=timezone.localdate() + timedelta(days=5),
            status=InvoiceStatus.SENT,
        )

        self.assertEqual(send_invoice_reminders(), 0)

    def test_reminder_uses_the_configured_from_address(self):
        from django.conf import settings

        _overdue_invoice(1)

        send_invoice_reminders()

        expected = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'noreply@tidebilling.com'
        self.assertEqual(mail.outbox[0].from_email, expected)


class MarkOverdueTests(AuthenticatedAPITestCase):
    def test_past_due_invoices_are_flagged(self):
        invoice = _overdue_invoice(3)

        count = mark_overdue_invoices()

        invoice.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertEqual(invoice.status, InvoiceStatus.OVERDUE)
        self.assertEqual(invoice.history.first().status_to, InvoiceStatus.OVERDUE)

    def test_future_invoices_are_left_alone(self):
        factories.make_invoice(
            due_date=timezone.localdate() + timedelta(days=3),
            status=InvoiceStatus.SENT,
        )

        self.assertEqual(mark_overdue_invoices(), 0)


class InvoiceEmailTests(AuthenticatedAPITestCase):
    def test_email_actually_attaches_the_pdf_it_promises(self):
        invoice = factories.make_invoice(total_amount=Decimal('100.00'))
        factories.make_invoice_item(invoice=invoice)

        self.assertTrue(send_invoice_email(invoice.id))

        self.assertEqual(len(mail.outbox), 1)
        attachments = mail.outbox[0].attachments
        self.assertEqual(len(attachments), 1)
        filename, content, mimetype = attachments[0]
        self.assertEqual(filename, f'{invoice.invoice_number}.pdf')
        self.assertEqual(mimetype, 'application/pdf')
        self.assertTrue(content.startswith(b'%PDF'))

    def test_sending_marks_the_invoice_sent(self):
        invoice = factories.make_invoice(total_amount=Decimal('10.00'))

        send_invoice_email(invoice.id)

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.SENT)


class OrderToInvoiceTests(AuthenticatedAPITestCase):
    def _order_with_items(self):
        order = factories.make_order()
        factories.make_order_item(
            order=order, quantity=2, unit_price=Decimal('50.00')
        )
        order.calculate_totals()
        return order

    def test_generate_invoice_action(self):
        order = self._order_with_items()

        response = self.client.post(
            reverse('order-generate-invoice', args=[order.id])
        )

        self.assertEqual(response.status_code, 201)
        invoice = Invoice.objects.get(order=order)
        self.assertEqual(invoice.total_amount, order.total_amount)
        self.assertEqual(invoice.items.count(), 1)

    def test_generating_twice_returns_the_same_invoice(self):
        order = self._order_with_items()

        first = self.client.post(
            reverse('order-generate-invoice', args=[order.id])
        )
        second = self.client.post(
            reverse('order-generate-invoice', args=[order.id])
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(Invoice.objects.filter(order=order).count(), 1)

    def test_generated_invoice_records_the_creating_user(self):
        order = self._order_with_items()

        self.client.post(reverse('order-generate-invoice', args=[order.id]))

        self.assertEqual(Invoice.objects.get(order=order).created_by, self.user)


class CustomerArchiveTests(AuthenticatedAPITestCase):
    def test_delete_archives_a_customer_with_financial_history(self):
        invoice = factories.make_invoice()
        customer = invoice.customer

        response = self.client.delete(
            reverse('customer-detail', args=[customer.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['archived'])
        customer.refresh_from_db()
        self.assertTrue(customer.is_archived)
        self.assertIsNotNone(customer.archived_at)
        self.assertFalse(customer.status)

    def test_delete_removes_a_customer_with_no_history(self):
        from customers.models import Customer

        customer = factories.make_customer()

        response = self.client.delete(
            reverse('customer-detail', args=[customer.id])
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Customer.objects.filter(pk=customer.pk).exists())

    def test_archive_and_unarchive_actions(self):
        customer = factories.make_customer()

        self.client.post(reverse('customer-archive', args=[customer.id]))
        customer.refresh_from_db()
        self.assertTrue(customer.is_archived)

        self.client.post(reverse('customer-unarchive', args=[customer.id]))
        customer.refresh_from_db()
        self.assertFalse(customer.is_archived)

    def test_active_queryset_excludes_archived(self):
        from customers.models import Customer

        keep = factories.make_customer()
        gone = factories.make_customer()
        gone.archive()

        self.assertEqual(list(Customer.objects.active()), [keep])
        self.assertEqual(list(Customer.objects.archived()), [gone])

    def test_statement_treats_credit_notes_as_reductions(self):
        """A credit note is money owed back; it must not inflate the total."""
        invoice = factories.make_invoice(total_amount=Decimal('220.00'))
        invoice.create_credit_note(Decimal('20.00'))

        response = self.client.get(
            reverse('customer-statement', args=[invoice.customer.id])
        )

        self.assertEqual(response.data['invoice_count'], 1)
        self.assertEqual(response.data['credit_note_count'], 1)
        self.assertEqual(response.data['total_invoiced'], '220.00')
        self.assertEqual(response.data['total_credited'], '20.00')
        self.assertEqual(response.data['total_outstanding'], '200.00')

    def test_statement_action(self):
        invoice = factories.make_invoice(total_amount=Decimal('100.00'))
        payment = factories.make_payment(invoice=invoice, amount=Decimal('40.00'))
        payment.mark_as_completed()

        response = self.client.get(
            reverse('customer-statement', args=[invoice.customer.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total_invoiced'], '100.00')
        self.assertEqual(response.data['total_paid'], '40.00')
        self.assertEqual(response.data['total_outstanding'], '60.00')
