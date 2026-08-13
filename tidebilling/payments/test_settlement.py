"""Refund settlement, idempotency and money constraints."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from invoices.models import InvoiceStatus
from payments.models import Payment, PaymentStateError, PaymentStatus, Refund
from tidebilling import factories
from tidebilling.apitest import AuthenticatedAPITestCase


class PaymentIdempotencyTests(AuthenticatedAPITestCase):
    def test_completing_twice_does_not_double_credit_the_invoice(self):
        invoice = factories.make_invoice(total_amount=Decimal('100.00'))
        payment = factories.make_payment(invoice=invoice, amount=Decimal('40.00'))

        payment.mark_as_completed()
        with self.assertRaises(PaymentStateError):
            payment.mark_as_completed()

        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal('40.00'))

    def test_completing_a_failed_payment_is_rejected(self):
        payment = factories.make_payment()
        payment.mark_as_failed('declined')

        with self.assertRaises(PaymentStateError):
            payment.mark_as_completed()

    def test_failing_a_completed_payment_is_rejected(self):
        invoice = factories.make_invoice(total_amount=Decimal('10.00'))
        payment = factories.make_payment(invoice=invoice, amount=Decimal('10.00'))
        payment.mark_as_completed()

        with self.assertRaises(PaymentStateError):
            payment.mark_as_failed('too late')

    def test_completion_records_the_acting_user(self):
        invoice = factories.make_invoice(total_amount=Decimal('10.00'))
        payment = factories.make_payment(invoice=invoice, amount=Decimal('10.00'))

        payment.mark_as_completed(user=self.user)

        payment.refresh_from_db()
        self.assertEqual(payment.processed_by, self.user)

    def test_completion_writes_invoice_history(self):
        invoice = factories.make_invoice(total_amount=Decimal('100.00'))
        payment = factories.make_payment(invoice=invoice, amount=Decimal('50.00'))

        payment.mark_as_completed(user=self.user)

        self.assertEqual(
            invoice.history.first().status_to, InvoiceStatus.PARTIALLY_PAID
        )


class RefundSettlementTests(AuthenticatedAPITestCase):
    def _completed_payment(self, total='100.00', paid='100.00'):
        invoice = factories.make_invoice(total_amount=Decimal(total))
        payment = factories.make_payment(invoice=invoice, amount=Decimal(paid))
        payment.mark_as_completed()
        return payment, invoice

    def test_full_refund_reopens_the_invoice(self):
        payment, invoice = self._completed_payment()
        refund = factories.make_refund(payment=payment, amount=Decimal('100.00'))

        refund.mark_as_completed(user=self.user)

        invoice.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal('0.00'))
        self.assertEqual(invoice.outstanding_amount, Decimal('100.00'))
        self.assertEqual(invoice.status, InvoiceStatus.REFUNDED)
        self.assertEqual(payment.status, PaymentStatus.REFUNDED)
        self.assertIsNone(invoice.paid_date)

    def test_partial_refund_marks_payment_partially_refunded(self):
        payment, invoice = self._completed_payment()
        refund = factories.make_refund(payment=payment, amount=Decimal('30.00'))

        refund.mark_as_completed()

        invoice.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal('70.00'))
        self.assertEqual(invoice.outstanding_amount, Decimal('30.00'))
        self.assertEqual(invoice.status, InvoiceStatus.PARTIALLY_PAID)
        self.assertEqual(payment.status, PaymentStatus.PARTIALLY_REFUNDED)

    def test_successive_partial_refunds_settle_to_fully_refunded(self):
        payment, invoice = self._completed_payment()
        factories.make_refund(payment=payment, amount=Decimal('60.00')).mark_as_completed()
        factories.make_refund(payment=payment, amount=Decimal('40.00')).mark_as_completed()

        payment.refresh_from_db()
        invoice.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.REFUNDED)
        self.assertEqual(invoice.paid_amount, Decimal('0.00'))

    def test_refund_is_idempotent(self):
        payment, invoice = self._completed_payment()
        refund = factories.make_refund(payment=payment, amount=Decimal('50.00'))
        refund.mark_as_completed()

        with self.assertRaises(PaymentStateError):
            refund.mark_as_completed()

        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal('50.00'))

    def test_cannot_refund_a_pending_payment(self):
        payment = factories.make_payment()
        refund = factories.make_refund(payment=payment, amount=Decimal('10.00'))

        with self.assertRaises(PaymentStateError):
            refund.mark_as_completed()

    def test_refunded_and_refundable_amounts(self):
        payment, _ = self._completed_payment()
        factories.make_refund(payment=payment, amount=Decimal('25.00')).mark_as_completed()

        payment.refresh_from_db()
        self.assertEqual(payment.refunded_amount, Decimal('25.00'))
        self.assertEqual(payment.refundable_amount, Decimal('75.00'))


class CumulativeRefundValidationTests(AuthenticatedAPITestCase):
    def test_cumulative_refunds_cannot_exceed_the_payment(self):
        payment = factories.make_payment(amount=Decimal('100.00'))
        Refund.objects.create(
            payment=payment, amount=Decimal('60.00'), reason='first'
        )

        second = Refund(payment=payment, amount=Decimal('50.00'), reason='second')
        with self.assertRaises(ValidationError):
            second.full_clean(exclude=['refund_reference'])

    def test_refunds_up_to_the_payment_total_are_allowed(self):
        payment = factories.make_payment(amount=Decimal('100.00'))
        Refund.objects.create(
            payment=payment, amount=Decimal('60.00'), reason='first'
        )

        second = Refund(payment=payment, amount=Decimal('40.00'), reason='second')
        second.full_clean(exclude=['refund_reference'])  # must not raise

    def test_api_rejects_a_second_refund_that_would_over_refund(self):
        payment = factories.make_payment(amount=Decimal('100.00'))
        first = self.client.post(
            reverse('payment-create-refund', args=[payment.id]),
            {'amount': '80.00', 'reason': 'partial'},
        )
        self.assertEqual(first.status_code, 201)

        second = self.client.post(
            reverse('payment-create-refund', args=[payment.id]),
            {'amount': '50.00', 'reason': 'too much'},
        )

        self.assertEqual(second.status_code, 400)
        self.assertEqual(Refund.objects.count(), 1)

    def test_refund_complete_action(self):
        invoice = factories.make_invoice(total_amount=Decimal('100.00'))
        payment = factories.make_payment(invoice=invoice, amount=Decimal('100.00'))
        payment.mark_as_completed()
        refund = factories.make_refund(payment=payment, amount=Decimal('40.00'))

        response = self.client.post(
            reverse('refund-complete', args=[refund.id])
        )

        self.assertEqual(response.status_code, 200)
        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal('60.00'))

    def test_refund_complete_rejects_pending_payment(self):
        payment = factories.make_payment()
        refund = factories.make_refund(payment=payment, amount=Decimal('10.00'))

        response = self.client.post(
            reverse('refund-complete', args=[refund.id])
        )

        self.assertEqual(response.status_code, 400)


class MoneyConstraintTests(AuthenticatedAPITestCase):
    def test_payment_amount_must_be_positive(self):
        invoice = factories.make_invoice()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Payment.objects.create(
                    invoice=invoice,
                    customer=invoice.customer,
                    amount=Decimal('-5.00'),
                    payment_method='cash',
                )

    def test_refund_amount_must_be_positive(self):
        payment = factories.make_payment()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Refund.objects.create(
                    payment=payment, amount=Decimal('-1.00'), reason='bad'
                )

    def test_payment_currency_must_match_invoice(self):
        invoice = factories.make_invoice(currency='USD')
        payment = Payment(
            invoice=invoice,
            customer=invoice.customer,
            amount=Decimal('10.00'),
            currency='EUR',
            payment_method='cash',
        )

        with self.assertRaises(ValidationError):
            payment.clean()

    def test_matching_currency_passes_validation(self):
        invoice = factories.make_invoice(currency='USD')
        payment = Payment(
            invoice=invoice,
            customer=invoice.customer,
            amount=Decimal('10.00'),
            currency='USD',
            payment_method='cash',
        )

        payment.clean()  # must not raise


class ProtectedDeletionTests(AuthenticatedAPITestCase):
    def test_customer_with_invoices_cannot_be_hard_deleted(self):
        from django.db.models import ProtectedError

        invoice = factories.make_invoice()

        with self.assertRaises(ProtectedError):
            invoice.customer.delete()

    def test_invoice_with_payments_cannot_be_hard_deleted(self):
        from django.db.models import ProtectedError

        payment = factories.make_payment()

        with self.assertRaises(ProtectedError):
            payment.invoice.delete()
