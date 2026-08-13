"""Project-level tests: routing, health check, auth and Celery tasks."""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.sessions.models import Session
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from invoices.models import Invoice, InvoiceStatus
from invoices.tasks import (
    generate_invoice_from_order,
    process_recurring_invoices,
    send_invoice_email,
    send_invoice_reminders,
)
from subscriptions.models import SubscriptionStatus
from subscriptions.tasks import (
    check_trial_expirations,
    process_subscription_renewals,
    send_subscription_expiry_warnings,
    update_subscription_usage,
)
from tidebilling import factories
from tidebilling.apitest import AuthenticatedAPITestCase
from tidebilling.tasks import cleanup_expired_sessions, generate_monthly_reports


class HealthCheckTests(TestCase):
    def test_health_check_is_public_and_reports_healthy(self):
        response = self.client.get('/health/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'healthy')
        self.assertEqual(response.json()['checks']['database'], 'ok')

    def test_health_check_is_reverseable(self):
        self.assertEqual(reverse('health-check'), '/health/')


class RoutingTests(AuthenticatedAPITestCase):
    def test_api_routes_are_not_double_nested(self):
        """Each router is mounted once under /api/v1/<app>/."""
        expected = {
            'customer-list': '/api/v1/customers/customers/',
            'customercontact-list': '/api/v1/customers/contacts/',
            'product-list': '/api/v1/products/products/',
            'order-list': '/api/v1/orders/orders/',
            'invoice-list': '/api/v1/invoices/invoices/',
            'payment-list': '/api/v1/payments/payments/',
            'subscription-list': '/api/v1/subscriptions/subscriptions/',
            'servicerequest-list': '/api/v1/services/requests/',
        }

        for name, path in expected.items():
            with self.subTest(name=name):
                self.assertEqual(reverse(name), path)
                self.assertNotIn('/api/api/', reverse(name))

    def test_every_router_root_resolves(self):
        for name in (
            'customer-list',
            'product-list',
            'category-list',
            'order-list',
            'invoice-list',
            'payment-list',
            'refund-list',
            'subscriptionplan-list',
            'subscription-list',
            'servicecategory-list',
            'service-list',
            'servicerequest-list',
        ):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_products_and_services_categories_do_not_collide(self):
        """Both apps register a `categories` route; app prefixes keep them distinct."""
        self.assertNotEqual(
            reverse('category-list'), reverse('servicecategory-list')
        )


class AuthTests(TestCase):
    def test_token_endpoint_issues_a_token(self):
        factories.make_user(username='authuser', password='secret123')

        response = self.client.post(
            reverse('api_token_auth'),
            {'username': 'authuser', 'password': 'secret123'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('token', response.json())

    def test_token_endpoint_rejects_bad_credentials(self):
        factories.make_user(username='authuser2', password='secret123')

        response = self.client.post(
            reverse('api_token_auth'),
            {'username': 'authuser2', 'password': 'wrong'},
        )

        self.assertEqual(response.status_code, 400)

    def test_endpoints_reject_anonymous_requests(self):
        response = self.client.get(reverse('customer-list'))

        self.assertEqual(response.status_code, 401)

    def test_issued_token_authenticates_api_calls(self):
        factories.make_user(username='authuser3', password='secret123')
        token = self.client.post(
            reverse('api_token_auth'),
            {'username': 'authuser3', 'password': 'secret123'},
        ).json()['token']

        response = self.client.get(
            reverse('customer-list'), HTTP_AUTHORIZATION=f'Token {token}'
        )

        self.assertEqual(response.status_code, 200)


class SchemaTests(AuthenticatedAPITestCase):
    def test_openapi_schema_generates(self):
        """Exercises every serializer/viewset through drf-spectacular."""
        response = self.client.get(reverse('schema'))

        self.assertEqual(response.status_code, 200)

    def test_swagger_and_redoc_render(self):
        for name in ('swagger-ui', 'redoc'):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)


class InvoiceTaskTests(TestCase):
    def test_generate_invoice_from_order_copies_items_and_totals(self):
        order = factories.make_order()
        product = factories.make_product(title='Widget')
        factories.make_order_item(
            order=order, product=product, quantity=2, unit_price=Decimal('50.00')
        )
        order.calculate_totals()

        invoice_id = generate_invoice_from_order(order.id)

        invoice = Invoice.objects.get(pk=invoice_id)
        self.assertEqual(invoice.customer, order.customer)
        self.assertEqual(invoice.order, order)
        self.assertEqual(invoice.total_amount, order.total_amount)
        self.assertEqual(invoice.items.count(), 1)
        self.assertEqual(invoice.items.first().description, 'Widget')

    def test_generate_invoice_from_unknown_order_returns_none(self):
        self.assertIsNone(
            generate_invoice_from_order('00000000-0000-0000-0000-000000000000')
        )

    def test_send_invoice_email_sends_and_marks_sent(self):
        invoice = factories.make_invoice(total_amount=Decimal('100.00'))

        result = send_invoice_email(invoice.id)

        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(invoice.invoice_number, mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, [invoice.customer.email])

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.SENT)

    def test_send_invoice_reminders_emails_and_flags_overdue(self):
        yesterday = timezone.now().date() - timedelta(days=1)
        overdue = factories.make_invoice(
            due_date=yesterday, status=InvoiceStatus.SENT
        )
        # Not overdue, and not in a chaseable status.
        factories.make_invoice(
            due_date=timezone.now().date() + timedelta(days=10),
            status=InvoiceStatus.SENT,
        )
        factories.make_invoice(due_date=yesterday, status=InvoiceStatus.PAID)

        send_invoice_reminders()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [overdue.customer.email])

        overdue.refresh_from_db()
        self.assertEqual(overdue.status, InvoiceStatus.OVERDUE)

    def test_process_recurring_invoices_clones_and_advances_schedule(self):
        today = date.today()
        source = factories.make_invoice(
            status=InvoiceStatus.PAID,
            is_recurring=True,
            recurring_frequency='monthly',
            next_invoice_date=today,
            total_amount=Decimal('110.00'),
        )
        factories.make_invoice_item(
            invoice=source, quantity=Decimal('1'), unit_price=Decimal('100.00')
        )

        process_recurring_invoices()

        clones = Invoice.objects.filter(
            customer=source.customer, is_recurring=True
        ).exclude(pk=source.pk)
        self.assertEqual(clones.count(), 1)
        self.assertEqual(clones.first().items.count(), 1)

        source.refresh_from_db()
        self.assertEqual(source.next_invoice_date, today + timedelta(days=30))

    def test_process_recurring_invoices_skips_future_schedules(self):
        factories.make_invoice(
            status=InvoiceStatus.PAID,
            is_recurring=True,
            recurring_frequency='monthly',
            next_invoice_date=date.today() + timedelta(days=10),
        )

        process_recurring_invoices()

        self.assertEqual(Invoice.objects.count(), 1)


class SubscriptionTaskTests(TestCase):
    def test_process_subscription_renewals_rolls_period_and_bills(self):
        subscription = factories.make_subscription(price=Decimal('100.00'))
        original_end = subscription.current_period_end
        subscription.next_billing_date = timezone.now() - timedelta(days=1)
        subscription.current_usage = {'api_calls': 500}
        subscription.save()

        process_subscription_renewals()

        subscription.refresh_from_db()
        self.assertEqual(subscription.current_period_start, original_end)
        self.assertEqual(
            subscription.current_period_end, original_end + timedelta(days=30)
        )
        self.assertEqual(subscription.current_usage, {})

        invoice = Invoice.objects.get(customer=subscription.customer)
        self.assertEqual(invoice.invoice_type, 'recurring')
        self.assertEqual(invoice.subtotal, Decimal('100.00'))

    def test_renewals_skip_subscriptions_cancelling_at_period_end(self):
        subscription = factories.make_subscription()
        subscription.next_billing_date = timezone.now() - timedelta(days=1)
        subscription.cancel_at_period_end = True
        subscription.save()

        process_subscription_renewals()

        self.assertEqual(Invoice.objects.count(), 0)

    def test_check_trial_expirations_activates_and_notifies(self):
        subscription = factories.make_subscription(
            status=SubscriptionStatus.TRIAL,
            trial_end_date=timezone.now() - timedelta(hours=1),
        )

        check_trial_expirations()

        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.ACTIVE)
        self.assertEqual(len(mail.outbox), 1)

    def test_check_trial_expirations_ignores_live_trials(self):
        factories.make_subscription(
            status=SubscriptionStatus.TRIAL,
            trial_end_date=timezone.now() + timedelta(days=3),
        )

        check_trial_expirations()

        self.assertEqual(len(mail.outbox), 0)

    def test_expiry_warnings_target_period_end_cancellations(self):
        subscription = factories.make_subscription()
        subscription.current_period_end = timezone.now() + timedelta(days=3)
        subscription.cancel_at_period_end = True
        subscription.save()

        send_subscription_expiry_warnings()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [subscription.customer.email])

    def test_update_subscription_usage_warns_once_over_limit(self):
        subscription = factories.make_subscription(
            usage_limits={'api_calls': 10}
        )

        result = update_subscription_usage(subscription.id, 'api_calls', 4)
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 0)

        update_subscription_usage(subscription.id, 'api_calls', 20)

        subscription.refresh_from_db()
        self.assertEqual(subscription.current_usage['api_calls'], 24)
        self.assertEqual(len(mail.outbox), 1)

    def test_update_subscription_usage_with_unknown_id_returns_false(self):
        self.assertFalse(
            update_subscription_usage(
                '00000000-0000-0000-0000-000000000000', 'api_calls', 1
            )
        )


class ProjectTaskTests(TestCase):
    def test_cleanup_expired_sessions_removes_only_expired(self):
        Session.objects.create(
            session_key='expired',
            session_data='x',
            expire_date=timezone.now() - timedelta(days=1),
        )
        Session.objects.create(
            session_key='live',
            session_data='x',
            expire_date=timezone.now() + timedelta(days=1),
        )

        removed = cleanup_expired_sessions()

        self.assertEqual(removed, 1)
        self.assertEqual(
            list(Session.objects.values_list('session_key', flat=True)), ['live']
        )

    def test_generate_monthly_reports_returns_totals_for_last_month(self):
        report = generate_monthly_reports()

        self.assertIn('period', report)
        self.assertIn('total_invoiced', report)
        self.assertIn('total_paid', report)
