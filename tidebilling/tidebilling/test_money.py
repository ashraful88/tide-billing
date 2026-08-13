"""Money rounding, currency and tax-rate snapshotting."""

from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from tidebilling import factories
from tidebilling.apitest import AuthenticatedAPITestCase
from tidebilling.money import apply_tax, default_tax_rate, money


class MoneyHelperTests(TestCase):
    def test_quantizes_to_two_places(self):
        self.assertEqual(money(Decimal('10.005')), Decimal('10.01'))
        self.assertEqual(money(Decimal('10.004')), Decimal('10.00'))

    def test_rounds_half_up_not_half_even(self):
        # Python's default banker's rounding would give 10.02 here.
        self.assertEqual(money(Decimal('10.015')), Decimal('10.02'))
        self.assertEqual(money(Decimal('10.025')), Decimal('10.03'))

    def test_accepts_non_decimal_input_without_float_error(self):
        self.assertEqual(money('19.99'), Decimal('19.99'))
        self.assertEqual(money(5), Decimal('5.00'))

    def test_apply_tax_returns_a_quantized_decimal(self):
        result = apply_tax(Decimal('33.33'), Decimal('0.10'))

        self.assertEqual(result, Decimal('3.33'))
        self.assertEqual(result.as_tuple().exponent, -2)

    def test_apply_tax_never_mixes_decimal_and_float(self):
        """The bug class that silently skipped subscription invoicing."""
        self.assertEqual(apply_tax(Decimal('100.00'), 0.1), Decimal('10.00'))

    @override_settings(TAX_RATE=0.06)
    def test_default_tax_rate_reads_settings(self):
        self.assertEqual(default_tax_rate(), Decimal('0.06'))


class TaxSnapshotTests(AuthenticatedAPITestCase):
    def test_invoice_snapshots_the_configured_rate(self):
        invoice = factories.make_invoice()

        self.assertEqual(invoice.tax_rate, default_tax_rate())

    @override_settings(TAX_RATE=0.06)
    def test_rate_change_does_not_alter_existing_invoices(self):
        existing = factories.make_invoice(tax_rate=Decimal('0.1000'))
        factories.make_invoice_item(
            invoice=existing, quantity=Decimal('1'), unit_price=Decimal('100.00')
        )
        existing.calculate_totals()

        self.assertEqual(existing.tax_amount, Decimal('10.00'))

    def test_invoice_honours_a_custom_rate(self):
        invoice = factories.make_invoice(tax_rate=Decimal('0.0600'))
        factories.make_invoice_item(
            invoice=invoice, quantity=Decimal('1'), unit_price=Decimal('100.00')
        )

        invoice.calculate_totals()

        self.assertEqual(invoice.tax_amount, Decimal('6.00'))
        self.assertEqual(invoice.total_amount, Decimal('106.00'))

    def test_order_honours_a_custom_rate(self):
        order = factories.make_order(tax_rate=Decimal('0.0600'))
        factories.make_order_item(
            order=order, quantity=1, unit_price=Decimal('100.00')
        )

        order.calculate_totals()

        self.assertEqual(order.tax_amount, Decimal('6.00'))

    def test_zero_tax_rate(self):
        invoice = factories.make_invoice(tax_rate=Decimal('0.0000'))
        factories.make_invoice_item(
            invoice=invoice, quantity=Decimal('1'), unit_price=Decimal('100.00')
        )

        invoice.calculate_totals()

        self.assertEqual(invoice.tax_amount, Decimal('0.00'))
        self.assertEqual(invoice.total_amount, Decimal('100.00'))


class RoundingTests(AuthenticatedAPITestCase):
    def test_totals_are_stored_at_two_places(self):
        invoice = factories.make_invoice()
        factories.make_invoice_item(
            invoice=invoice, quantity=Decimal('3'), unit_price=Decimal('33.33')
        )

        invoice.calculate_totals()

        self.assertEqual(invoice.subtotal, Decimal('99.99'))
        self.assertEqual(invoice.tax_amount, Decimal('10.00'))
        self.assertEqual(invoice.total_amount, Decimal('109.99'))
        for value in (invoice.subtotal, invoice.tax_amount, invoice.total_amount):
            self.assertEqual(value.as_tuple().exponent, -2)

    def test_in_memory_value_matches_the_persisted_value(self):
        """Un-quantized intermediates used to disagree with the DB column."""
        invoice = factories.make_invoice()
        factories.make_invoice_item(
            invoice=invoice, quantity=Decimal('7'), unit_price=Decimal('14.29')
        )

        invoice.calculate_totals()
        in_memory = invoice.tax_amount
        invoice.refresh_from_db()

        self.assertEqual(in_memory, invoice.tax_amount)

    def test_item_total_price_is_quantized(self):
        item = factories.make_invoice_item(
            quantity=Decimal('3'), unit_price=Decimal('0.335')
        )

        self.assertEqual(item.total_price.as_tuple().exponent, -2)


class CurrencyTests(AuthenticatedAPITestCase):
    def test_invoice_has_a_currency_defaulting_from_settings(self):
        from django.conf import settings

        invoice = factories.make_invoice()

        self.assertEqual(invoice.currency, settings.CURRENCY_CODE)

    def test_order_has_a_currency(self):
        from django.conf import settings

        self.assertEqual(factories.make_order().currency, settings.CURRENCY_CODE)

    def test_invoice_from_order_inherits_currency_and_rate(self):
        from invoices.models import Invoice
        from invoices.tasks import generate_invoice_from_order

        order = factories.make_order(
            currency='MYR', tax_rate=Decimal('0.0600')
        )
        factories.make_order_item(order=order, unit_price=Decimal('100.00'))
        order.calculate_totals()

        invoice = Invoice.objects.get(pk=generate_invoice_from_order(order.id))

        self.assertEqual(invoice.currency, 'MYR')
        self.assertEqual(invoice.tax_rate, Decimal('0.0600'))

    def test_currency_is_exposed_on_the_api(self):
        invoice = factories.make_invoice()

        response = self.client.get(reverse('invoice-detail', args=[invoice.id]))

        self.assertIn('currency', response.data)
