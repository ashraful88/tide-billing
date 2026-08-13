from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from invoices.models import (
    Invoice,
    InvoiceHistory,
    InvoiceStatus,
    InvoiceType,
    PaymentTerms,
)
from tidebilling import factories
from tidebilling.apitest import AuthenticatedAPITestCase


class InvoiceNumberTests(AuthenticatedAPITestCase):
    def test_invoice_number_generated_on_first_save(self):
        invoice = factories.make_invoice()

        self.assertRegex(invoice.invoice_number, r'^INV-\d{4}-\d{6}$')

    def test_invoice_number_is_stable_across_saves(self):
        invoice = factories.make_invoice()
        original = invoice.invoice_number

        invoice.notes = 'changed'
        invoice.save()

        self.assertEqual(invoice.invoice_number, original)

    def test_invoice_numbers_are_unique(self):
        numbers = {factories.make_invoice().invoice_number for _ in range(10)}

        self.assertEqual(len(numbers), 10)


class InvoiceDueDateTests(AuthenticatedAPITestCase):
    def test_due_date_defaults_to_net_30(self):
        issue = date(2026, 1, 1)
        invoice = factories.make_invoice(issue_date=issue)

        self.assertEqual(invoice.payment_terms, PaymentTerms.NET_30)
        self.assertEqual(invoice.due_date, issue + timedelta(days=30))

    def test_due_date_follows_payment_terms(self):
        issue = date(2026, 1, 1)
        expected = {
            PaymentTerms.NET_15: 15,
            PaymentTerms.NET_30: 30,
            PaymentTerms.NET_45: 45,
            PaymentTerms.NET_60: 60,
            PaymentTerms.DUE_ON_RECEIPT: 0,
        }

        for terms, days in expected.items():
            with self.subTest(terms=terms):
                invoice = factories.make_invoice(
                    issue_date=issue, payment_terms=terms
                )
                self.assertEqual(
                    invoice.due_date, issue + timedelta(days=days)
                )

    def test_explicit_due_date_is_respected(self):
        explicit = date(2026, 6, 1)
        invoice = factories.make_invoice(
            issue_date=date(2026, 1, 1), due_date=explicit
        )

        self.assertEqual(invoice.due_date, explicit)


class InvoiceTotalsTests(AuthenticatedAPITestCase):
    def test_outstanding_amount_computed_on_save(self):
        invoice = factories.make_invoice(
            total_amount=Decimal('100.00'), paid_amount=Decimal('30.00')
        )

        self.assertEqual(invoice.outstanding_amount, Decimal('70.00'))

    def test_calculate_totals_sums_items_and_applies_tax(self):
        invoice = factories.make_invoice()
        factories.make_invoice_item(
            invoice=invoice, quantity=Decimal('2'), unit_price=Decimal('100.00')
        )
        factories.make_invoice_item(
            invoice=invoice, quantity=Decimal('1'), unit_price=Decimal('50.00')
        )

        invoice.calculate_totals()

        self.assertEqual(invoice.subtotal, Decimal('250.00'))
        self.assertEqual(invoice.tax_amount, Decimal('25.00'))
        self.assertEqual(invoice.total_amount, Decimal('275.00'))
        self.assertEqual(invoice.outstanding_amount, Decimal('275.00'))

    def test_calculate_totals_applies_discount(self):
        invoice = factories.make_invoice(discount_amount=Decimal('10.00'))
        factories.make_invoice_item(
            invoice=invoice, quantity=Decimal('1'), unit_price=Decimal('100.00')
        )

        invoice.calculate_totals()

        # 100 subtotal + 10 tax - 10 discount
        self.assertEqual(invoice.total_amount, Decimal('100.00'))

    def test_calculate_totals_accounts_for_existing_payments(self):
        invoice = factories.make_invoice(paid_amount=Decimal('50.00'))
        factories.make_invoice_item(
            invoice=invoice, quantity=Decimal('1'), unit_price=Decimal('100.00')
        )

        invoice.calculate_totals()

        self.assertEqual(invoice.outstanding_amount, Decimal('60.00'))

    def test_item_total_price_is_derived(self):
        item = factories.make_invoice_item(
            quantity=Decimal('3'), unit_price=Decimal('9.50')
        )

        self.assertEqual(item.total_price, Decimal('28.50'))

    def test_item_total_price_recalculated_on_update(self):
        item = factories.make_invoice_item(
            quantity=Decimal('1'), unit_price=Decimal('10.00')
        )

        item.quantity = Decimal('4')
        item.save()

        self.assertEqual(item.total_price, Decimal('40.00'))


class InvoiceStateTests(AuthenticatedAPITestCase):
    def test_default_status_is_draft(self):
        self.assertEqual(factories.make_invoice().status, InvoiceStatus.DRAFT)

    def test_mark_as_sent(self):
        invoice = factories.make_invoice()

        invoice.mark_as_sent()

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.SENT)
        self.assertIsNotNone(invoice.sent_date)

    def test_mark_as_paid_clears_outstanding(self):
        invoice = factories.make_invoice(total_amount=Decimal('200.00'))

        invoice.mark_as_paid()

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.PAID)
        self.assertEqual(invoice.paid_amount, Decimal('200.00'))
        self.assertEqual(invoice.outstanding_amount, Decimal('0.00'))
        self.assertIsNotNone(invoice.paid_date)

    def test_mark_as_paid_accepts_explicit_date(self):
        invoice = factories.make_invoice(total_amount=Decimal('10.00'))
        when = timezone.now() - timedelta(days=3)

        invoice.mark_as_paid(payment_date=when)

        self.assertEqual(invoice.paid_date, when)

    def test_is_overdue_true_when_past_due(self):
        invoice = factories.make_invoice(
            due_date=timezone.now().date() - timedelta(days=1),
            status=InvoiceStatus.SENT,
        )

        self.assertTrue(invoice.is_overdue)

    def test_is_overdue_false_when_due_in_future(self):
        invoice = factories.make_invoice(
            due_date=timezone.now().date() + timedelta(days=5),
            status=InvoiceStatus.SENT,
        )

        self.assertFalse(invoice.is_overdue)

    def test_is_overdue_false_for_paid_and_cancelled(self):
        past = timezone.now().date() - timedelta(days=10)

        for status in (InvoiceStatus.PAID, InvoiceStatus.CANCELLED):
            with self.subTest(status=status):
                invoice = factories.make_invoice(due_date=past, status=status)
                self.assertFalse(invoice.is_overdue)

    def test_history_str(self):
        invoice = factories.make_invoice()
        history = InvoiceHistory.objects.create(
            invoice=invoice,
            status_from=InvoiceStatus.DRAFT,
            status_to=InvoiceStatus.SENT,
        )

        self.assertEqual(
            str(history), f'Invoice {invoice.invoice_number}: draft → sent'
        )


class InvoiceAPITests(AuthenticatedAPITestCase):
    def test_requires_authentication(self):
        self.unauthenticate()
        self.assertEqual(self.client.get(reverse('invoice-list')).status_code, 401)

    def test_create_sets_created_by(self):
        customer = factories.make_customer()

        response = self.client.post(
            reverse('invoice-list'),
            {
                'customer': str(customer.id),
                'due_date': '2026-12-31',
            },
        )

        self.assertEqual(response.status_code, 201)
        invoice = Invoice.objects.get(pk=response.data['id'])
        self.assertEqual(invoice.created_by, self.user)

    def test_send_action(self):
        invoice = factories.make_invoice()

        response = self.client.post(reverse('invoice-send', args=[invoice.id]))

        self.assertEqual(response.status_code, 200)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.SENT)

    def test_add_item_action_recalculates_totals(self):
        invoice = factories.make_invoice()

        response = self.client.post(
            reverse('invoice-add-item', args=[invoice.id]),
            {'description': 'Consulting', 'quantity': '2', 'unit_price': '100.00'},
        )

        self.assertEqual(response.status_code, 201)
        invoice.refresh_from_db()
        self.assertEqual(invoice.subtotal, Decimal('200.00'))
        self.assertEqual(invoice.total_amount, Decimal('220.00'))

    def test_add_item_rejects_invalid_payload(self):
        invoice = factories.make_invoice()

        response = self.client.post(
            reverse('invoice-add-item', args=[invoice.id]), {'quantity': '1'}
        )

        self.assertEqual(response.status_code, 400)

    def test_overdue_action(self):
        yesterday = timezone.now().date() - timedelta(days=1)
        factories.make_invoice(due_date=yesterday, status=InvoiceStatus.SENT)
        factories.make_invoice(
            due_date=yesterday, status=InvoiceStatus.PARTIALLY_PAID
        )
        # Excluded: not past due, and not in a chaseable status.
        factories.make_invoice(
            due_date=timezone.now().date() + timedelta(days=5),
            status=InvoiceStatus.SENT,
        )
        factories.make_invoice(due_date=yesterday, status=InvoiceStatus.PAID)
        factories.make_invoice(due_date=yesterday, status=InvoiceStatus.DRAFT)

        response = self.client.get(reverse('invoice-overdue'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)

    def test_due_soon_default_window(self):
        factories.make_invoice(
            due_date=timezone.now().date() + timedelta(days=3),
            status=InvoiceStatus.SENT,
        )
        factories.make_invoice(
            due_date=timezone.now().date() + timedelta(days=30),
            status=InvoiceStatus.SENT,
        )

        response = self.client.get(reverse('invoice-due-soon'))

        self.assertEqual(len(response.data), 1)

    def test_due_soon_honours_days_param(self):
        factories.make_invoice(
            due_date=timezone.now().date() + timedelta(days=20),
            status=InvoiceStatus.SENT,
        )

        response = self.client.get(reverse('invoice-due-soon'), {'days': 30})

        self.assertEqual(len(response.data), 1)

    def test_items_action(self):
        invoice = factories.make_invoice()
        factories.make_invoice_item(invoice=invoice)
        factories.make_invoice_item()

        response = self.client.get(reverse('invoice-items', args=[invoice.id]))

        self.assertEqual(len(response.data), 1)

    def test_list_serializer_exposes_overdue_flag_and_item_count(self):
        invoice = factories.make_invoice(
            due_date=timezone.now().date() - timedelta(days=1),
            status=InvoiceStatus.SENT,
        )
        factories.make_invoice_item(invoice=invoice)

        response = self.client.get(reverse('invoice-list'))

        row = response.data['results'][0]
        self.assertTrue(row['is_overdue'])
        self.assertEqual(row['item_count'], 1)

    def test_detail_serializer_nests_customer_and_order(self):
        order = factories.make_order()
        invoice = factories.make_invoice(customer=order.customer, order=order)

        response = self.client.get(reverse('invoice-detail', args=[invoice.id]))

        self.assertEqual(response.data['customer']['id'], str(order.customer.id))
        self.assertEqual(response.data['order']['id'], str(order.id))

    def test_invoice_number_is_read_only(self):
        customer = factories.make_customer()

        response = self.client.post(
            reverse('invoice-list'),
            {
                'customer': str(customer.id),
                'due_date': '2026-12-31',
                'invoice_number': 'ATTACKER-SET',
            },
        )

        self.assertNotEqual(response.data['invoice_number'], 'ATTACKER-SET')

    def test_filter_by_status_and_type(self):
        factories.make_invoice(status=InvoiceStatus.DRAFT)
        factories.make_invoice(
            status=InvoiceStatus.SENT, invoice_type=InvoiceType.RECURRING
        )

        response = self.client.get(
            reverse('invoice-list'), {'invoice_type': InvoiceType.RECURRING}
        )

        self.assertEqual(response.data['count'], 1)

    def test_invoice_item_viewset_filters_by_invoice(self):
        invoice = factories.make_invoice()
        factories.make_invoice_item(invoice=invoice)
        factories.make_invoice_item()

        response = self.client.get(
            reverse('invoiceitem-list'), {'invoice': str(invoice.id)}
        )

        self.assertEqual(response.data['count'], 1)
