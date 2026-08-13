from decimal import Decimal

from django.urls import reverse

from invoices.models import InvoiceStatus
from payments.models import Payment, PaymentGateway, PaymentStatus, Refund
from tidebilling import factories
from tidebilling.apitest import AuthenticatedAPITestCase


class PaymentModelTests(AuthenticatedAPITestCase):
    def test_payment_reference_generated_on_first_save(self):
        payment = factories.make_payment()

        self.assertRegex(payment.payment_reference, r'^PAY-\d{8}-[0-9A-F]{8}$')

    def test_payment_reference_is_stable_across_saves(self):
        payment = factories.make_payment()
        original = payment.payment_reference

        payment.notes = 'changed'
        payment.save()

        self.assertEqual(payment.payment_reference, original)

    def test_references_are_unique(self):
        refs = {factories.make_payment().payment_reference for _ in range(10)}

        self.assertEqual(len(refs), 10)

    def test_defaults(self):
        payment = factories.make_payment()

        self.assertEqual(payment.status, PaymentStatus.PENDING)
        self.assertEqual(payment.payment_gateway, PaymentGateway.MANUAL)
        self.assertEqual(payment.currency, 'USD')

    def test_str(self):
        customer = factories.make_customer(name='Acme')
        invoice = factories.make_invoice(customer=customer)
        payment = factories.make_payment(
            invoice=invoice, amount=Decimal('50.00')
        )

        self.assertEqual(
            str(payment),
            f'Payment {payment.payment_reference} - Acme - 50.00',
        )


class PaymentCompletionTests(AuthenticatedAPITestCase):
    def test_full_payment_marks_invoice_paid(self):
        invoice = factories.make_invoice(total_amount=Decimal('100.00'))
        payment = factories.make_payment(
            invoice=invoice, amount=Decimal('100.00')
        )

        payment.mark_as_completed()

        self.assertEqual(payment.status, PaymentStatus.COMPLETED)
        self.assertIsNotNone(payment.processed_at)

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.PAID)
        self.assertEqual(invoice.paid_amount, Decimal('100.00'))
        self.assertEqual(invoice.outstanding_amount, Decimal('0.00'))

    def test_overpayment_still_marks_invoice_paid(self):
        invoice = factories.make_invoice(total_amount=Decimal('100.00'))
        payment = factories.make_payment(
            invoice=invoice, amount=Decimal('150.00')
        )

        payment.mark_as_completed()

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.PAID)
        self.assertEqual(invoice.outstanding_amount, Decimal('0.00'))

    def test_partial_payment_marks_invoice_partially_paid(self):
        invoice = factories.make_invoice(total_amount=Decimal('100.00'))
        payment = factories.make_payment(
            invoice=invoice, amount=Decimal('40.00')
        )

        payment.mark_as_completed()

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.PARTIALLY_PAID)
        self.assertEqual(invoice.paid_amount, Decimal('40.00'))
        self.assertEqual(invoice.outstanding_amount, Decimal('60.00'))

    def test_successive_partial_payments_settle_the_invoice(self):
        invoice = factories.make_invoice(total_amount=Decimal('100.00'))

        factories.make_payment(
            invoice=invoice, amount=Decimal('60.00')
        ).mark_as_completed()
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.PARTIALLY_PAID)

        second = factories.make_payment(
            invoice=Payment.objects.filter(invoice=invoice).first().invoice,
            amount=Decimal('40.00'),
        )
        second.invoice.refresh_from_db()
        second.mark_as_completed()

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.PAID)
        self.assertEqual(invoice.outstanding_amount, Decimal('0.00'))

    def test_mark_as_failed_records_reason(self):
        payment = factories.make_payment()

        payment.mark_as_failed('card declined')

        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.FAILED)
        self.assertEqual(payment.failure_reason, 'card declined')

    def test_mark_as_failed_without_reason(self):
        payment = factories.make_payment()

        payment.mark_as_failed()

        self.assertEqual(payment.status, PaymentStatus.FAILED)
        self.assertEqual(payment.failure_reason, '')


class RefundModelTests(AuthenticatedAPITestCase):
    def test_refund_reference_generated(self):
        refund = factories.make_refund()

        self.assertRegex(refund.refund_reference, r'^REF-\d{8}-[0-9A-F]{8}$')

    def test_str(self):
        refund = factories.make_refund(amount=Decimal('25.00'))

        self.assertEqual(
            str(refund), f'Refund {refund.refund_reference} - 25.00'
        )


class StoredPaymentMethodTests(AuthenticatedAPITestCase):
    def test_setting_a_new_default_unsets_the_previous_one(self):
        customer = factories.make_customer()
        first = factories.make_payment_method(customer=customer, is_default=True)
        second = factories.make_payment_method(customer=customer, is_default=True)

        first.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)

    def test_default_is_scoped_per_customer(self):
        a = factories.make_payment_method(is_default=True)
        b = factories.make_payment_method(is_default=True)

        a.refresh_from_db()
        self.assertTrue(a.is_default)
        self.assertTrue(b.is_default)

    def test_resaving_the_default_keeps_it_default(self):
        method = factories.make_payment_method(is_default=True)

        method.card_brand = 'Visa'
        method.save()

        method.refresh_from_db()
        self.assertTrue(method.is_default)

    def test_str_prefers_card_description(self):
        with_card = factories.make_payment_method(
            last_four_digits='4242', card_brand='Visa'
        )
        self.assertEqual(str(with_card), 'Visa ending in 4242')

        customer = factories.make_customer(name='Acme')
        without_card = factories.make_payment_method(
            customer=customer, type='cash'
        )
        self.assertEqual(str(without_card), 'cash for Acme')


class PaymentAPITests(AuthenticatedAPITestCase):
    def test_requires_authentication(self):
        self.unauthenticate()
        self.assertEqual(self.client.get(reverse('payment-list')).status_code, 401)

    def test_create_sets_processed_by(self):
        invoice = factories.make_invoice()

        response = self.client.post(
            reverse('payment-list'),
            {
                'customer': str(invoice.customer.id),
                'invoice': str(invoice.id),
                'amount': '50.00',
                'payment_method': 'credit_card',
            },
        )

        self.assertEqual(response.status_code, 201)
        payment = Payment.objects.get(pk=response.data['id'])
        self.assertEqual(payment.processed_by, self.user)

    def test_gateway_response_is_write_only(self):
        invoice = factories.make_invoice()

        response = self.client.post(
            reverse('payment-list'),
            {
                'customer': str(invoice.customer.id),
                'invoice': str(invoice.id),
                'amount': '50.00',
                'payment_method': 'credit_card',
                'gateway_response': {'raw': 'secret'},
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertNotIn('gateway_response', response.data)

    def test_mark_completed_action(self):
        invoice = factories.make_invoice(total_amount=Decimal('75.00'))
        payment = factories.make_payment(
            invoice=invoice, amount=Decimal('75.00')
        )

        response = self.client.post(
            reverse('payment-mark-completed', args=[payment.id])
        )

        self.assertEqual(response.status_code, 200)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.PAID)

    def test_mark_completed_rejects_non_pending_payment(self):
        payment = factories.make_payment(status=PaymentStatus.COMPLETED)

        response = self.client.post(
            reverse('payment-mark-completed', args=[payment.id])
        )

        self.assertEqual(response.status_code, 400)

    def test_mark_failed_action(self):
        payment = factories.make_payment()

        response = self.client.post(
            reverse('payment-mark-failed', args=[payment.id]),
            {'reason': 'insufficient funds'},
        )

        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.FAILED)
        self.assertEqual(payment.failure_reason, 'insufficient funds')

    def test_create_refund_action(self):
        payment = factories.make_payment(amount=Decimal('100.00'))

        response = self.client.post(
            reverse('payment-create-refund', args=[payment.id]),
            {'amount': '40.00', 'reason': 'partial return'},
        )

        self.assertEqual(response.status_code, 201)
        refund = Refund.objects.get(payment=payment)
        self.assertEqual(refund.amount, Decimal('40.00'))
        self.assertEqual(refund.processed_by, self.user)

    def test_create_refund_requires_amount(self):
        payment = factories.make_payment()

        response = self.client.post(
            reverse('payment-create-refund', args=[payment.id]), {}
        )

        self.assertEqual(response.status_code, 400)

    def test_create_refund_rejects_amount_above_payment(self):
        payment = factories.make_payment(amount=Decimal('100.00'))

        response = self.client.post(
            reverse('payment-create-refund', args=[payment.id]),
            {'amount': '150.00'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Refund.objects.count(), 0)

    def test_create_refund_rejects_non_positive_amount(self):
        payment = factories.make_payment(amount=Decimal('100.00'))

        response = self.client.post(
            reverse('payment-create-refund', args=[payment.id]),
            {'amount': '0'},
        )

        self.assertEqual(response.status_code, 400)

    def test_create_refund_rejects_unparseable_amount(self):
        payment = factories.make_payment(amount=Decimal('100.00'))

        response = self.client.post(
            reverse('payment-create-refund', args=[payment.id]),
            {'amount': 'not-a-number'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Refund.objects.count(), 0)

    def test_list_serializer_shape(self):
        payment = factories.make_payment()

        response = self.client.get(reverse('payment-list'))

        row = response.data['results'][0]
        self.assertEqual(row['invoice_number'], payment.invoice.invoice_number)
        self.assertNotIn('gateway_transaction_id', row)

    def test_detail_serializer_nests_invoice_and_refunds(self):
        payment = factories.make_payment()
        factories.make_refund(payment=payment)

        response = self.client.get(reverse('payment-detail', args=[payment.id]))

        self.assertEqual(
            response.data['invoice']['id'], str(payment.invoice.id)
        )
        self.assertEqual(len(response.data['refunds']), 1)

    def test_filter_by_status(self):
        factories.make_payment(status=PaymentStatus.PENDING)
        factories.make_payment(status=PaymentStatus.COMPLETED)

        response = self.client.get(
            reverse('payment-list'), {'status': PaymentStatus.COMPLETED}
        )

        self.assertEqual(response.data['count'], 1)

    def test_refund_viewset_lists_refunds(self):
        factories.make_refund()

        response = self.client.get(reverse('refund-list'))

        self.assertEqual(response.data['count'], 1)

    def test_stored_payment_method_tokens_are_write_only(self):
        customer = factories.make_customer()

        response = self.client.post(
            reverse('storedpaymentmethod-list'),
            {
                'customer': str(customer.id),
                'type': 'credit_card',
                'stripe_payment_method_id': 'pm_secret',
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertNotIn('stripe_payment_method_id', response.data)
