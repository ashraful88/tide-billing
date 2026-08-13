from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from subscriptions.models import (
    BillingFrequency,
    Subscription,
    SubscriptionChange,
    SubscriptionStatus,
    SubscriptionUsage,
)
from tidebilling import factories
from tidebilling.apitest import AuthenticatedAPITestCase


class SubscriptionPlanTests(AuthenticatedAPITestCase):
    def test_str(self):
        plan = factories.make_plan(name='Pro', price=Decimal('50.00'))

        self.assertEqual(str(plan), 'Pro - 50.00/monthly')

    def test_monthly_price_for_every_billing_frequency(self):
        """monthly_price must stay Decimal-safe for all frequencies."""
        expected = {
            BillingFrequency.DAILY: Decimal('3000'),
            BillingFrequency.WEEKLY: Decimal('433'),
            BillingFrequency.MONTHLY: Decimal('100'),
            BillingFrequency.QUARTERLY: Decimal('33.33'),
            BillingFrequency.SEMI_ANNUALLY: Decimal('16.67'),
            BillingFrequency.ANNUALLY: Decimal('8.33'),
        }

        for frequency, approx in expected.items():
            with self.subTest(frequency=frequency):
                plan = factories.make_plan(
                    price=Decimal('100.00'), billing_frequency=frequency
                )
                self.assertAlmostEqual(
                    Decimal(plan.monthly_price), approx, places=1
                )

    def test_defaults(self):
        plan = factories.make_plan()

        self.assertTrue(plan.is_active)
        self.assertFalse(plan.is_featured)
        self.assertEqual(plan.trial_period_days, 0)
        self.assertEqual(plan.features, [])

    def test_ordering_is_by_price(self):
        expensive = factories.make_plan(price=Decimal('300.00'))
        cheap = factories.make_plan(price=Decimal('10.00'))

        self.assertEqual(
            list(type(cheap).objects.all()), [cheap, expensive]
        )


class SubscriptionModelTests(AuthenticatedAPITestCase):
    def test_subscription_number_generated(self):
        subscription = factories.make_subscription()

        self.assertRegex(
            subscription.subscription_number, r'^SUB-\d{8}-[0-9A-F]{8}$'
        )

    def test_price_defaults_to_plan_price(self):
        plan = factories.make_plan(price=Decimal('75.00'))
        subscription = factories.make_subscription(plan=plan)

        self.assertEqual(subscription.price, Decimal('75.00'))

    def test_explicit_price_overrides_plan(self):
        plan = factories.make_plan(price=Decimal('75.00'))
        subscription = factories.make_subscription(
            plan=plan, price=Decimal('20.00')
        )

        self.assertEqual(subscription.price, Decimal('20.00'))

    def test_billing_dates_derived_from_frequency(self):
        expected = {
            BillingFrequency.DAILY: 1,
            BillingFrequency.WEEKLY: 7,
            BillingFrequency.MONTHLY: 30,
            BillingFrequency.QUARTERLY: 90,
            BillingFrequency.SEMI_ANNUALLY: 180,
            BillingFrequency.ANNUALLY: 365,
        }

        for frequency, days in expected.items():
            with self.subTest(frequency=frequency):
                plan = factories.make_plan(billing_frequency=frequency)
                start = timezone.now()
                subscription = factories.make_subscription(
                    plan=plan, start_date=start
                )

                self.assertEqual(
                    subscription.current_period_start, start
                )
                self.assertEqual(
                    subscription.current_period_end,
                    start + timedelta(days=days),
                )
                self.assertEqual(
                    subscription.next_billing_date,
                    subscription.current_period_end,
                )

    def test_is_in_trial(self):
        future = factories.make_subscription(
            trial_end_date=timezone.now() + timedelta(days=5)
        )
        past = factories.make_subscription(
            trial_end_date=timezone.now() - timedelta(days=5)
        )
        none = factories.make_subscription()

        self.assertTrue(future.is_in_trial())
        self.assertFalse(past.is_in_trial())
        self.assertFalse(none.is_in_trial())

    def test_cancel_at_period_end_keeps_subscription_active(self):
        subscription = factories.make_subscription()

        subscription.cancel(reason='too expensive', at_period_end=True)

        subscription.refresh_from_db()
        self.assertTrue(subscription.cancel_at_period_end)
        self.assertIsNotNone(subscription.cancelled_at)
        self.assertEqual(subscription.cancellation_reason, 'too expensive')
        self.assertEqual(subscription.status, SubscriptionStatus.ACTIVE)
        self.assertIsNone(subscription.end_date)

    def test_cancel_immediately(self):
        subscription = factories.make_subscription()

        subscription.cancel(reason='fraud', at_period_end=False)

        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.CANCELLED)
        self.assertIsNotNone(subscription.end_date)

    def test_reactivate_restores_cancelled_subscription(self):
        subscription = factories.make_subscription()
        subscription.cancel(at_period_end=False)

        subscription.reactivate()

        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.ACTIVE)
        self.assertFalse(subscription.cancel_at_period_end)
        self.assertIsNone(subscription.cancelled_at)
        self.assertIsNone(subscription.end_date)

    def test_reactivate_is_a_noop_for_non_cancelled(self):
        subscription = factories.make_subscription(
            status=SubscriptionStatus.SUSPENDED
        )

        subscription.reactivate()

        self.assertEqual(subscription.status, SubscriptionStatus.SUSPENDED)

    def test_upgrade_plan_switches_plan_and_price(self):
        old_plan = factories.make_plan(price=Decimal('10.00'))
        new_plan = factories.make_plan(price=Decimal('30.00'))
        subscription = factories.make_subscription(plan=old_plan)

        subscription.upgrade_plan(new_plan)

        subscription.refresh_from_db()
        self.assertEqual(subscription.plan, new_plan)
        self.assertEqual(subscription.price, Decimal('30.00'))

    def test_upgrade_plan_records_the_change(self):
        old_plan = factories.make_plan(price=Decimal('10.00'))
        new_plan = factories.make_plan(price=Decimal('30.00'))
        subscription = factories.make_subscription(plan=old_plan)

        subscription.upgrade_plan(new_plan)

        change = SubscriptionChange.objects.get(subscription=subscription)
        self.assertEqual(change.change_type, 'plan_upgrade')
        self.assertEqual(change.old_plan, old_plan)
        self.assertEqual(change.new_plan, new_plan)
        self.assertEqual(change.new_price, Decimal('30.00'))
        # The audit row must preserve what the customer was paying before.
        self.assertEqual(change.old_price, Decimal('10.00'))

    def test_add_usage_accumulates(self):
        subscription = factories.make_subscription()

        subscription.add_usage('api_calls', 5)
        subscription.add_usage('api_calls', 7)
        subscription.add_usage('storage_gb', 2)

        subscription.refresh_from_db()
        self.assertEqual(subscription.current_usage['api_calls'], 12)
        self.assertEqual(subscription.current_usage['storage_gb'], 2)

    def test_str(self):
        customer = factories.make_customer(name='Acme')
        subscription = factories.make_subscription(customer=customer)

        self.assertEqual(
            str(subscription),
            f'Subscription {subscription.subscription_number} - Acme',
        )


class SubscriptionUsageModelTests(AuthenticatedAPITestCase):
    def test_str_and_uniqueness_scope(self):
        subscription = factories.make_subscription()
        start = timezone.now()
        usage = SubscriptionUsage.objects.create(
            subscription=subscription,
            metric_name='api_calls',
            usage_amount=Decimal('10.00'),
            billing_period_start=start,
            billing_period_end=start + timedelta(days=30),
        )

        self.assertEqual(
            str(usage),
            f'{subscription.subscription_number} - api_calls: 10.00',
        )


class SubscriptionPlanAPITests(AuthenticatedAPITestCase):
    def test_requires_authentication(self):
        self.unauthenticate()
        self.assertEqual(
            self.client.get(reverse('subscriptionplan-list')).status_code, 401
        )

    def test_list_serializes_non_monthly_plans(self):
        """monthly_price is a serializer field, so a bad multiplier 500s here."""
        factories.make_plan(billing_frequency=BillingFrequency.ANNUALLY)
        factories.make_plan(billing_frequency=BillingFrequency.WEEKLY)

        response = self.client.get(reverse('subscriptionplan-list'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 2)

    def test_active_action(self):
        factories.make_plan(is_active=True)
        factories.make_plan(is_active=False)

        response = self.client.get(reverse('subscriptionplan-active'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)


class SubscriptionAPITests(AuthenticatedAPITestCase):
    def test_create_sets_created_by(self):
        customer = factories.make_customer()
        plan = factories.make_plan()

        response = self.client.post(
            reverse('subscription-list'),
            {'customer': str(customer.id), 'plan': str(plan.id), 'price': '10.00'},
        )

        self.assertEqual(response.status_code, 201)
        subscription = Subscription.objects.get(pk=response.data['id'])
        self.assertEqual(subscription.created_by, self.user)

    def test_cancel_action_at_period_end(self):
        subscription = factories.make_subscription()

        response = self.client.post(
            reverse('subscription-cancel', args=[subscription.id]),
            {'reason': 'churn', 'at_period_end': True},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        subscription.refresh_from_db()
        self.assertTrue(subscription.cancel_at_period_end)
        self.assertEqual(subscription.status, SubscriptionStatus.ACTIVE)

    def test_cancel_action_immediately(self):
        subscription = factories.make_subscription()

        response = self.client.post(
            reverse('subscription-cancel', args=[subscription.id]),
            {'reason': 'churn', 'at_period_end': False},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.CANCELLED)

    def test_reactivate_action(self):
        subscription = factories.make_subscription()
        subscription.cancel(at_period_end=False)

        response = self.client.post(
            reverse('subscription-reactivate', args=[subscription.id])
        )

        self.assertEqual(response.status_code, 200)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.ACTIVE)

    def test_reactivate_rejects_active_subscription(self):
        subscription = factories.make_subscription()

        response = self.client.post(
            reverse('subscription-reactivate', args=[subscription.id])
        )

        self.assertEqual(response.status_code, 400)

    def test_upgrade_action(self):
        subscription = factories.make_subscription()
        new_plan = factories.make_plan(price=Decimal('99.00'))

        response = self.client.post(
            reverse('subscription-upgrade', args=[subscription.id]),
            {'plan_id': str(new_plan.id)},
        )

        self.assertEqual(response.status_code, 200)
        subscription.refresh_from_db()
        self.assertEqual(subscription.plan, new_plan)

    def test_upgrade_requires_plan_id(self):
        subscription = factories.make_subscription()

        response = self.client.post(
            reverse('subscription-upgrade', args=[subscription.id]), {}
        )

        self.assertEqual(response.status_code, 400)

    def test_upgrade_with_unknown_plan_returns_404(self):
        subscription = factories.make_subscription()

        response = self.client.post(
            reverse('subscription-upgrade', args=[subscription.id]),
            {'plan_id': '00000000-0000-0000-0000-000000000000'},
        )

        self.assertEqual(response.status_code, 404)

    def test_add_usage_action(self):
        subscription = factories.make_subscription()

        response = self.client.post(
            reverse('subscription-add-usage', args=[subscription.id]),
            {'metric': 'api_calls', 'amount': 10},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        subscription.refresh_from_db()
        self.assertEqual(subscription.current_usage['api_calls'], 10)

    def test_add_usage_requires_metric_and_amount(self):
        subscription = factories.make_subscription()

        response = self.client.post(
            reverse('subscription-add-usage', args=[subscription.id]),
            {'metric': 'api_calls'},
        )

        self.assertEqual(response.status_code, 400)

    def test_add_usage_rejects_non_numeric_amount(self):
        subscription = factories.make_subscription()

        response = self.client.post(
            reverse('subscription-add-usage', args=[subscription.id]),
            {'metric': 'api_calls', 'amount': 'lots'},
        )

        self.assertEqual(response.status_code, 400)

    def test_expiring_soon_action(self):
        soon = factories.make_subscription()
        soon.current_period_end = timezone.now() + timedelta(days=3)
        soon.save()

        later = factories.make_subscription()
        later.current_period_end = timezone.now() + timedelta(days=60)
        later.save()

        response = self.client.get(reverse('subscription-expiring-soon'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_expiring_soon_honours_days_param(self):
        subscription = factories.make_subscription()
        subscription.current_period_end = timezone.now() + timedelta(days=45)
        subscription.save()

        response = self.client.get(
            reverse('subscription-expiring-soon'), {'days': 90}
        )

        self.assertEqual(len(response.data), 1)

    def test_detail_serializer_nests_plan_and_changes(self):
        subscription = factories.make_subscription()
        subscription.upgrade_plan(factories.make_plan())

        response = self.client.get(
            reverse('subscription-detail', args=[subscription.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('plan', response.data)
        self.assertEqual(len(response.data['changes']), 1)

    def test_changes_viewset_is_read_only(self):
        subscription = factories.make_subscription()
        subscription.upgrade_plan(factories.make_plan())

        listing = self.client.get(reverse('subscriptionchange-list'))
        self.assertEqual(listing.data['count'], 1)

        create = self.client.post(reverse('subscriptionchange-list'), {})
        self.assertEqual(create.status_code, 405)

    def test_usage_viewset_is_read_only(self):
        create = self.client.post(reverse('subscriptionusage-list'), {})

        self.assertEqual(create.status_code, 405)
