"""Proration, period-end cancellation and usage-based overage billing."""

from datetime import timedelta
from decimal import Decimal

from django.core import mail
from django.urls import reverse
from django.utils import timezone

from invoices.models import Invoice
from subscriptions.models import SubscriptionChange, SubscriptionStatus
from subscriptions.tasks import (
    check_trial_expirations,
    expire_period_end_cancellations,
    process_subscription_renewals,
)
from tidebilling import factories
from tidebilling.apitest import AuthenticatedAPITestCase


class ProrationTests(AuthenticatedAPITestCase):
    def _subscription_at_half_period(self, price='100.00'):
        plan = factories.make_plan(price=Decimal(price))
        subscription = factories.make_subscription(plan=plan)
        now = timezone.now()
        subscription.current_period_start = now - timedelta(days=15)
        subscription.current_period_end = now + timedelta(days=15)
        subscription.save()
        return subscription

    def test_unused_fraction_is_about_half_mid_period(self):
        subscription = self._subscription_at_half_period()

        fraction = subscription.unused_period_fraction()

        self.assertAlmostEqual(float(fraction), 0.5, places=2)

    def test_unused_fraction_is_zero_after_period_end(self):
        subscription = factories.make_subscription()
        subscription.current_period_start = timezone.now() - timedelta(days=60)
        subscription.current_period_end = timezone.now() - timedelta(days=30)
        subscription.save()

        self.assertEqual(subscription.unused_period_fraction(), Decimal('0.00'))

    def test_upgrade_charges_the_prorated_difference(self):
        subscription = self._subscription_at_half_period('100.00')
        pricier = factories.make_plan(price=Decimal('200.00'))

        change = subscription.change_plan(pricier, user=self.user)

        # Half a period of the 100 credit against half of the 200 charge.
        self.assertEqual(change.change_type, 'plan_upgrade')
        self.assertAlmostEqual(float(change.proration_amount), 50.0, delta=1.0)

    def test_downgrade_produces_a_credit(self):
        subscription = self._subscription_at_half_period('200.00')
        cheaper = factories.make_plan(price=Decimal('100.00'))

        change = subscription.change_plan(cheaper, user=self.user)

        self.assertEqual(change.change_type, 'plan_downgrade')
        self.assertLess(change.proration_amount, Decimal('0.00'))

    def test_same_price_change_is_recorded_as_price_change(self):
        subscription = self._subscription_at_half_period('100.00')
        same = factories.make_plan(price=Decimal('100.00'))

        change = subscription.change_plan(same)

        self.assertEqual(change.change_type, 'price_change')
        self.assertEqual(change.proration_amount, Decimal('0.00'))

    def test_proration_can_be_disabled(self):
        subscription = self._subscription_at_half_period('100.00')
        pricier = factories.make_plan(price=Decimal('200.00'))

        change = subscription.change_plan(pricier, prorate=False)

        self.assertEqual(change.proration_amount, Decimal('0.00'))

    def test_change_records_old_and_new_price(self):
        subscription = self._subscription_at_half_period('100.00')
        pricier = factories.make_plan(price=Decimal('150.00'))

        change = subscription.change_plan(pricier)

        self.assertEqual(change.old_price, Decimal('100.00'))
        self.assertEqual(change.new_price, Decimal('150.00'))
        subscription.refresh_from_db()
        self.assertEqual(subscription.price, Decimal('150.00'))

    def test_upgrade_api_returns_the_proration(self):
        subscription = self._subscription_at_half_period('100.00')
        pricier = factories.make_plan(price=Decimal('200.00'))

        response = self.client.post(
            reverse('subscription-upgrade', args=[subscription.id]),
            {'plan_id': str(pricier.id)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('proration_amount', response.data['change'])
        self.assertEqual(response.data['change']['change_type'], 'plan_upgrade')


class PeriodEndCancellationTests(AuthenticatedAPITestCase):
    def test_cancellation_completes_once_the_period_ends(self):
        subscription = factories.make_subscription()
        subscription.cancel(at_period_end=True)
        subscription.current_period_end = timezone.now() - timedelta(hours=1)
        subscription.save()

        expired = expire_period_end_cancellations()

        subscription.refresh_from_db()
        self.assertEqual(expired, 1)
        self.assertEqual(subscription.status, SubscriptionStatus.CANCELLED)
        self.assertIsNotNone(subscription.end_date)

    def test_cancellation_waits_until_the_period_ends(self):
        subscription = factories.make_subscription()
        subscription.cancel(at_period_end=True)
        subscription.current_period_end = timezone.now() + timedelta(days=5)
        subscription.save()

        expire_period_end_cancellations()

        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.ACTIVE)

    def test_active_subscription_without_the_flag_is_untouched(self):
        subscription = factories.make_subscription()
        subscription.current_period_end = timezone.now() - timedelta(days=1)
        subscription.save()

        expire_period_end_cancellations()

        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.ACTIVE)

    def test_expire_if_period_ended_is_idempotent(self):
        subscription = factories.make_subscription()
        subscription.cancel(at_period_end=True)
        subscription.current_period_end = timezone.now() - timedelta(hours=1)
        subscription.save()

        self.assertTrue(subscription.expire_if_period_ended())
        self.assertFalse(subscription.expire_if_period_ended())


class RenewalBillingTests(AuthenticatedAPITestCase):
    def _due_subscription(self, **kwargs):
        subscription = factories.make_subscription(
            price=Decimal('100.00'), **kwargs
        )
        subscription.next_billing_date = timezone.now() - timedelta(hours=1)
        subscription.save()
        return subscription

    def test_renewal_invoice_has_a_line_item_and_totals(self):
        subscription = self._due_subscription()

        process_subscription_renewals()

        invoice = Invoice.objects.get(customer=subscription.customer)
        self.assertEqual(invoice.items.count(), 1)
        self.assertEqual(invoice.subtotal, Decimal('100.00'))
        self.assertEqual(invoice.tax_amount, Decimal('10.00'))
        self.assertEqual(invoice.total_amount, Decimal('110.00'))

    def test_renewal_bills_usage_overage(self):
        subscription = self._due_subscription(
            usage_limits={'api_calls': {'limit': 100, 'unit_price': '0.50'}}
        )
        subscription.current_usage = {'api_calls': 140}
        subscription.save()

        process_subscription_renewals()

        invoice = Invoice.objects.get(customer=subscription.customer)
        descriptions = [item.description for item in invoice.items.all()]
        self.assertEqual(len(descriptions), 2)
        self.assertTrue(any('overage' in d for d in descriptions))
        # 40 calls over the limit at 0.50 = 20.00 on top of the 100.00 plan.
        self.assertEqual(invoice.subtotal, Decimal('120.00'))

    def test_usage_within_the_limit_is_not_billed(self):
        subscription = self._due_subscription(
            usage_limits={'api_calls': {'limit': 100, 'unit_price': '0.50'}}
        )
        subscription.current_usage = {'api_calls': 60}
        subscription.save()

        process_subscription_renewals()

        invoice = Invoice.objects.get(customer=subscription.customer)
        self.assertEqual(invoice.items.count(), 1)

    def test_limit_without_unit_price_is_not_billed(self):
        subscription = self._due_subscription(usage_limits={'api_calls': 10})
        subscription.current_usage = {'api_calls': 500}
        subscription.save()

        process_subscription_renewals()

        invoice = Invoice.objects.get(customer=subscription.customer)
        self.assertEqual(invoice.items.count(), 1)

    def test_renewal_carries_unbilled_proration(self):
        subscription = self._due_subscription()
        pricier = factories.make_plan(price=Decimal('200.00'))
        subscription.change_plan(pricier)
        subscription.next_billing_date = timezone.now() - timedelta(hours=1)
        subscription.save()

        process_subscription_renewals()

        invoice = Invoice.objects.get(customer=subscription.customer)
        descriptions = [item.description for item in invoice.items.all()]
        self.assertTrue(any('Proration' in d for d in descriptions))

    def test_proration_is_billed_only_once(self):
        subscription = self._due_subscription()
        pricier = factories.make_plan(price=Decimal('200.00'))
        subscription.change_plan(pricier)
        subscription.next_billing_date = timezone.now() - timedelta(hours=1)
        subscription.save()

        process_subscription_renewals()
        self.assertTrue(
            SubscriptionChange.objects.filter(proration_invoiced=True).exists()
        )

        subscription.refresh_from_db()
        subscription.next_billing_date = timezone.now() - timedelta(hours=1)
        subscription.save()
        process_subscription_renewals()

        second = Invoice.objects.filter(
            customer=subscription.customer
        ).order_by('created_at').last()
        self.assertFalse(
            any('Proration' in i.description for i in second.items.all())
        )

    def test_renewal_advances_the_period_and_clears_usage(self):
        subscription = self._due_subscription()
        original_end = subscription.current_period_end
        subscription.current_usage = {'api_calls': 5}
        subscription.save()

        process_subscription_renewals()

        subscription.refresh_from_db()
        self.assertEqual(subscription.current_period_start, original_end)
        self.assertEqual(subscription.current_usage, {})

    def test_renewal_is_not_repeated_within_the_same_period(self):
        subscription = self._due_subscription()

        process_subscription_renewals()
        process_subscription_renewals()

        self.assertEqual(
            Invoice.objects.filter(customer=subscription.customer).count(), 1
        )


class TrialConversionTests(AuthenticatedAPITestCase):
    def test_expired_trial_converts_and_notifies(self):
        subscription = factories.make_subscription(
            status=SubscriptionStatus.TRIAL,
            trial_end_date=timezone.now() - timedelta(hours=1),
        )

        converted = check_trial_expirations()

        subscription.refresh_from_db()
        self.assertEqual(converted, 1)
        self.assertEqual(subscription.status, SubscriptionStatus.ACTIVE)
        self.assertEqual(len(mail.outbox), 1)


class BeatScheduleTests(AuthenticatedAPITestCase):
    def test_every_periodic_task_is_scheduled(self):
        """Three tasks previously existed but were never in the schedule."""
        from tidebilling.celery import app

        scheduled = {entry['task'] for entry in app.conf.beat_schedule.values()}

        for task in (
            'invoices.tasks.process_recurring_invoices',
            'invoices.tasks.send_invoice_reminders',
            'invoices.tasks.mark_overdue_invoices',
            'subscriptions.tasks.process_subscription_renewals',
            'subscriptions.tasks.check_trial_expirations',
            'subscriptions.tasks.expire_period_end_cancellations',
            'subscriptions.tasks.send_subscription_expiry_warnings',
            'tidebilling.tasks.cleanup_expired_sessions',
        ):
            with self.subTest(task=task):
                self.assertIn(task, scheduled)
