"""Numbering, immutability, credit notes and audit history."""

import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from invoices.models import (
    Invoice,
    InvoiceFinalizedError,
    InvoiceHistory,
    InvoiceStatus,
    InvoiceType,
)
from invoices.numbering import DocumentSequence, allocate
from tidebilling import factories
from tidebilling.apitest import AuthenticatedAPITestCase


class SequentialNumberingTests(TestCase):
    def test_numbers_are_sequential_and_gapless(self):
        numbers = [factories.make_invoice().invoice_number for _ in range(5)]
        suffixes = [int(n.split('-')[-1]) for n in numbers]

        self.assertEqual(suffixes, [1, 2, 3, 4, 5])

    def test_number_embeds_the_issue_year(self):
        invoice = factories.make_invoice(issue_date=datetime.date(2026, 3, 1))

        self.assertTrue(invoice.invoice_number.startswith('INV-2026-'))

    def test_sequence_resets_per_year(self):
        first_2026 = factories.make_invoice(issue_date=datetime.date(2026, 5, 1))
        first_2027 = factories.make_invoice(issue_date=datetime.date(2027, 1, 4))

        self.assertEqual(first_2026.invoice_number, 'INV-2026-000001')
        self.assertEqual(first_2027.invoice_number, 'INV-2027-000001')

    def test_credit_notes_use_their_own_series(self):
        invoice = factories.make_invoice(total_amount=Decimal('100.00'))

        note = invoice.create_credit_note(Decimal('20.00'))

        self.assertTrue(note.invoice_number.startswith('CRN-'))
        # The invoice series is untouched by credit-note allocation.
        self.assertTrue(invoice.invoice_number.startswith('INV-'))

    def test_allocate_is_zero_padded(self):
        self.assertRegex(allocate('TST', 2026), r'^TST-2026-000001$')

    def test_sequence_row_tracks_last_value(self):
        factories.make_invoice()
        factories.make_invoice()

        sequence = DocumentSequence.objects.get(prefix='INV')
        self.assertEqual(sequence.last_value, 2)

    def test_number_is_not_regenerated_on_update(self):
        invoice = factories.make_invoice()
        original = invoice.invoice_number

        invoice.notes = 'edited'
        invoice.save()

        self.assertEqual(invoice.invoice_number, original)


class ImmutabilityTests(AuthenticatedAPITestCase):
    def test_draft_invoice_can_be_recalculated(self):
        invoice = factories.make_invoice()
        factories.make_invoice_item(invoice=invoice, unit_price=Decimal('10.00'))

        invoice.calculate_totals()

        self.assertEqual(invoice.subtotal, Decimal('10.00'))

    def test_issued_invoice_refuses_recalculation(self):
        invoice = factories.make_invoice()
        factories.make_invoice_item(invoice=invoice, unit_price=Decimal('10.00'))
        invoice.mark_as_sent()

        with self.assertRaises(InvoiceFinalizedError):
            invoice.calculate_totals()

    def test_is_finalized_flag(self):
        self.assertFalse(factories.make_invoice().is_finalized)
        for status in (
            InvoiceStatus.SENT,
            InvoiceStatus.PAID,
            InvoiceStatus.CANCELLED,
        ):
            with self.subTest(status=status):
                self.assertTrue(
                    factories.make_invoice(status=status).is_finalized
                )

    def test_api_rejects_editing_an_issued_invoice(self):
        invoice = factories.make_invoice()
        invoice.mark_as_sent()

        response = self.client.patch(
            reverse('invoice-detail', args=[invoice.id]), {'notes': 'tampered'}
        )

        self.assertEqual(response.status_code, 409)

    def test_api_rejects_deleting_an_issued_invoice(self):
        invoice = factories.make_invoice()
        invoice.mark_as_sent()

        response = self.client.delete(
            reverse('invoice-detail', args=[invoice.id])
        )

        self.assertEqual(response.status_code, 409)
        self.assertTrue(Invoice.objects.filter(pk=invoice.pk).exists())

    def test_draft_invoice_can_still_be_edited_and_deleted(self):
        invoice = factories.make_invoice()

        patch = self.client.patch(
            reverse('invoice-detail', args=[invoice.id]), {'notes': 'draft edit'}
        )
        self.assertEqual(patch.status_code, 200)

        delete = self.client.delete(reverse('invoice-detail', args=[invoice.id]))
        self.assertEqual(delete.status_code, 204)

    def test_api_rejects_adding_items_to_an_issued_invoice(self):
        invoice = factories.make_invoice()
        invoice.mark_as_sent()

        response = self.client.post(
            reverse('invoice-add-item', args=[invoice.id]),
            {'description': 'Sneaky', 'quantity': '1', 'unit_price': '99.00'},
        )

        self.assertEqual(response.status_code, 409)


class CreditNoteTests(AuthenticatedAPITestCase):
    def test_credit_note_leaves_the_original_untouched(self):
        invoice = factories.make_invoice(total_amount=Decimal('100.00'))

        note = invoice.create_credit_note(Decimal('30.00'), reason='Goodwill')

        invoice.refresh_from_db()
        self.assertEqual(invoice.total_amount, Decimal('100.00'))
        self.assertEqual(note.invoice_type, InvoiceType.CREDIT_NOTE)
        self.assertEqual(note.total_amount, Decimal('30.00'))
        self.assertEqual(note.original_invoice, invoice)
        self.assertEqual(note.notes, 'Goodwill')

    def test_credit_note_defaults_to_the_full_invoice_total(self):
        invoice = factories.make_invoice(total_amount=Decimal('80.00'))

        note = invoice.create_credit_note()

        self.assertEqual(note.total_amount, Decimal('80.00'))

    def test_credit_notes_cannot_exceed_the_invoice_total(self):
        invoice = factories.make_invoice(total_amount=Decimal('100.00'))
        invoice.create_credit_note(Decimal('60.00'))

        with self.assertRaises(ValidationError):
            invoice.create_credit_note(Decimal('50.00'))

    def test_credit_note_rejects_non_positive_amount(self):
        invoice = factories.make_invoice(total_amount=Decimal('100.00'))

        with self.assertRaises(ValidationError):
            invoice.create_credit_note(Decimal('0.00'))

    def test_a_credit_note_cannot_be_credit_noted(self):
        invoice = factories.make_invoice(total_amount=Decimal('100.00'))
        note = invoice.create_credit_note(Decimal('10.00'))

        with self.assertRaises(ValidationError):
            note.create_credit_note(Decimal('5.00'))

    def test_credit_note_inherits_currency_and_tax_rate(self):
        invoice = factories.make_invoice(
            total_amount=Decimal('100.00'),
            currency='MYR',
            tax_rate=Decimal('0.0600'),
        )

        note = invoice.create_credit_note(Decimal('10.00'))

        self.assertEqual(note.currency, 'MYR')
        self.assertEqual(note.tax_rate, Decimal('0.0600'))

    def test_credit_note_api_action(self):
        invoice = factories.make_invoice(total_amount=Decimal('100.00'))

        response = self.client.post(
            reverse('invoice-credit-note', args=[invoice.id]),
            {'amount': '25.00', 'reason': 'Returned goods'},
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['invoice_number'].startswith('CRN-'))

    def test_credit_note_api_rejects_over_credit(self):
        invoice = factories.make_invoice(total_amount=Decimal('50.00'))

        response = self.client.post(
            reverse('invoice-credit-note', args=[invoice.id]),
            {'amount': '500.00'},
        )

        self.assertEqual(response.status_code, 400)


class AuditHistoryTests(AuthenticatedAPITestCase):
    def test_mark_as_sent_writes_history(self):
        invoice = factories.make_invoice()

        invoice.mark_as_sent(user=self.user)

        entry = InvoiceHistory.objects.get(invoice=invoice)
        self.assertEqual(entry.status_from, InvoiceStatus.DRAFT)
        self.assertEqual(entry.status_to, InvoiceStatus.SENT)
        self.assertEqual(entry.changed_by, self.user)

    def test_mark_as_paid_writes_history(self):
        invoice = factories.make_invoice(total_amount=Decimal('10.00'))
        invoice.mark_as_sent()

        invoice.mark_as_paid()

        self.assertEqual(
            list(
                InvoiceHistory.objects.filter(invoice=invoice)
                .order_by('changed_at')
                .values_list('status_to', flat=True)
            ),
            [InvoiceStatus.SENT, InvoiceStatus.PAID],
        )

    def test_no_history_row_for_a_no_op_transition(self):
        invoice = factories.make_invoice()

        invoice.record_status_change(
            InvoiceStatus.DRAFT, InvoiceStatus.DRAFT, 'nothing changed'
        )

        self.assertEqual(InvoiceHistory.objects.count(), 0)

    def test_cancel_action_records_reason(self):
        invoice = factories.make_invoice()

        response = self.client.post(
            reverse('invoice-cancel', args=[invoice.id]),
            {'reason': 'Duplicate'},
        )

        self.assertEqual(response.status_code, 200)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.CANCELLED)
        self.assertEqual(
            InvoiceHistory.objects.get(invoice=invoice).notes, 'Duplicate'
        )

    def test_cancel_rejects_a_paid_invoice(self):
        invoice = factories.make_invoice(
            total_amount=Decimal('10.00'), status=InvoiceStatus.PAID
        )

        response = self.client.post(reverse('invoice-cancel', args=[invoice.id]))

        self.assertEqual(response.status_code, 400)

    def test_history_action(self):
        invoice = factories.make_invoice()
        invoice.mark_as_sent()

        response = self.client.get(
            reverse('invoice-history', args=[invoice.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)


class InvoicePdfTests(AuthenticatedAPITestCase):
    def test_pdf_action_returns_a_pdf(self):
        invoice = factories.make_invoice(total_amount=Decimal('100.00'))
        factories.make_invoice_item(invoice=invoice)

        response = self.client.get(reverse('invoice-pdf', args=[invoice.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))
        self.assertIn(invoice.invoice_number, response['Content-Disposition'])

    def test_pdf_renders_for_a_credit_note(self):
        from tidebilling.pdf import render_invoice_pdf

        invoice = factories.make_invoice(total_amount=Decimal('100.00'))
        note = invoice.create_credit_note(Decimal('10.00'))

        self.assertTrue(render_invoice_pdf(note).startswith(b'%PDF'))


class ArAgingTests(AuthenticatedAPITestCase):
    def test_aging_buckets_by_days_overdue(self):

        today = timezone.localdate()
        for days, amount in ((-5, '10.00'), (10, '20.00'), (45, '30.00'), (120, '40.00')):
            invoice = factories.make_invoice(
                due_date=today - datetime.timedelta(days=days),
                status=InvoiceStatus.SENT,
                total_amount=Decimal(amount),
            )
            invoice.outstanding_amount = Decimal(amount)
            invoice.save()

        response = self.client.get(reverse('invoice-aging'))

        self.assertEqual(response.status_code, 200)
        buckets = response.data['buckets']
        self.assertEqual(buckets['current']['amount'], '10.00')
        self.assertEqual(buckets['1-30']['amount'], '20.00')
        self.assertEqual(buckets['31-60']['amount'], '30.00')
        self.assertEqual(buckets['90+']['amount'], '40.00')
        self.assertEqual(response.data['total_outstanding'], '100.00')

    def test_aging_excludes_credit_notes(self):
        invoice = factories.make_invoice(
            due_date=timezone.localdate(),
            status=InvoiceStatus.SENT,
            total_amount=Decimal('100.00'),
        )
        invoice.outstanding_amount = Decimal('100.00')
        invoice.save()
        note = invoice.create_credit_note(Decimal('30.00'))
        note.mark_as_sent()

        response = self.client.get(reverse('invoice-aging'))

        # Without the exclusion the credit note would add 30 to receivables.
        self.assertEqual(response.data['total_outstanding'], '100.00')
