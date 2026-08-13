"""Role-based access control."""

from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.urls import reverse

from tidebilling import factories
from tidebilling.apitest import AuthenticatedAPITestCase, grant_role
from tidebilling.permissions import (
    ADMIN_GROUP,
    BILLING_GROUP,
    READONLY_GROUP,
    is_admin,
    is_billing_staff,
)


class RoleHelperTests(AuthenticatedAPITestCase):
    role = None  # exercise the helpers directly

    def test_unprovisioned_user_has_no_write_roles(self):
        user = factories.make_user()

        self.assertFalse(is_admin(user))
        self.assertFalse(is_billing_staff(user))

    def test_billing_role(self):
        user = grant_role(factories.make_user(), BILLING_GROUP)

        self.assertTrue(is_billing_staff(user))
        self.assertFalse(is_admin(user))

    def test_admin_role_implies_billing(self):
        user = grant_role(factories.make_user(), ADMIN_GROUP)

        self.assertTrue(is_admin(user))
        self.assertTrue(is_billing_staff(user))

    def test_superuser_bypasses_group_checks(self):
        user = factories.make_user(is_superuser=True)

        self.assertTrue(is_admin(user))
        self.assertTrue(is_billing_staff(user))


class SetupRolesCommandTests(AuthenticatedAPITestCase):
    def test_command_creates_all_three_groups(self):
        call_command('setup_roles', verbosity=0)

        for name in (ADMIN_GROUP, BILLING_GROUP, READONLY_GROUP):
            with self.subTest(name=name):
                self.assertTrue(Group.objects.filter(name=name).exists())

    def test_command_is_idempotent(self):
        call_command('setup_roles', verbosity=0)
        call_command('setup_roles', verbosity=0)

        self.assertEqual(Group.objects.filter(name=ADMIN_GROUP).count(), 1)

    def test_readonly_group_gets_only_view_permissions(self):
        call_command('setup_roles', verbosity=0)

        codenames = Group.objects.get(name=READONLY_GROUP).permissions.values_list(
            'codename', flat=True
        )
        self.assertTrue(codenames)
        self.assertTrue(all(c.startswith('view_') for c in codenames))


class ReadOnlyRoleTests(AuthenticatedAPITestCase):
    role = READONLY_GROUP

    def test_can_read(self):
        factories.make_invoice()

        self.assertEqual(
            self.client.get(reverse('invoice-list')).status_code, 200
        )

    def test_cannot_create(self):
        customer = factories.make_customer()

        response = self.client.post(
            reverse('invoice-list'),
            {'customer': str(customer.id), 'due_date': '2026-12-31'},
        )

        self.assertEqual(response.status_code, 403)

    def test_cannot_record_a_payment(self):
        invoice = factories.make_invoice(total_amount=Decimal('10.00'))
        payment = factories.make_payment(invoice=invoice, amount=Decimal('10.00'))

        response = self.client.post(
            reverse('payment-mark-completed', args=[payment.id])
        )

        self.assertEqual(response.status_code, 403)

    def test_cannot_delete(self):
        invoice = factories.make_invoice()

        response = self.client.delete(
            reverse('invoice-detail', args=[invoice.id])
        )

        self.assertEqual(response.status_code, 403)


class BillingRoleTests(AuthenticatedAPITestCase):
    role = BILLING_GROUP

    def test_can_create_an_invoice(self):
        customer = factories.make_customer()

        response = self.client.post(
            reverse('invoice-list'),
            {'customer': str(customer.id), 'due_date': '2026-12-31'},
        )

        self.assertEqual(response.status_code, 201)

    def test_can_record_a_payment(self):
        invoice = factories.make_invoice(total_amount=Decimal('10.00'))
        payment = factories.make_payment(invoice=invoice, amount=Decimal('10.00'))

        response = self.client.post(
            reverse('payment-mark-completed', args=[payment.id])
        )

        self.assertEqual(response.status_code, 200)

    def test_cannot_delete(self):
        """Billing staff correct mistakes by cancelling, not deleting."""
        invoice = factories.make_invoice()

        response = self.client.delete(
            reverse('invoice-detail', args=[invoice.id])
        )

        self.assertEqual(response.status_code, 403)


class AdminRoleTests(AuthenticatedAPITestCase):
    role = ADMIN_GROUP

    def test_can_delete_a_draft_invoice(self):
        invoice = factories.make_invoice()

        response = self.client.delete(
            reverse('invoice-detail', args=[invoice.id])
        )

        self.assertEqual(response.status_code, 204)


class UnprovisionedUserTests(AuthenticatedAPITestCase):
    role = None

    def test_authenticated_but_roleless_user_is_read_only(self):
        factories.make_invoice()

        self.assertEqual(
            self.client.get(reverse('invoice-list')).status_code, 200
        )

        customer = factories.make_customer()
        response = self.client.post(
            reverse('invoice-list'),
            {'customer': str(customer.id), 'due_date': '2026-12-31'},
        )
        self.assertEqual(response.status_code, 403)

    def test_anonymous_is_rejected(self):
        self.unauthenticate()

        self.assertEqual(
            self.client.get(reverse('invoice-list')).status_code, 401
        )
