"""Shared base class for API-level tests.

Named ``apitest.py`` so Django's ``test*.py`` discovery pattern does not collect
it as a test module.
"""

from django.contrib.auth.models import Group
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from tidebilling import factories
from tidebilling.permissions import ADMIN_GROUP, BILLING_GROUP, READONLY_GROUP


def grant_role(user, role):
    """Put ``user`` in a role group, creating the group on demand."""
    group, _ = Group.objects.get_or_create(name=role)
    user.groups.add(group)
    return user


class AuthenticatedAPITestCase(APITestCase):
    """APITestCase pre-authenticated with a token.

    Auth is DRF ``TokenAuthentication`` with role-based permissions, so the
    test user is placed in a role group. Defaults to ``admin`` so tests that
    are not about authorization can exercise every endpoint; override ``role``
    to assert what a narrower role can and cannot do.
    """

    role = ADMIN_GROUP

    def setUp(self):
        super().setUp()
        self.user = factories.make_user(username='tester')
        if self.role:
            grant_role(self.user, self.role)
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

    def unauthenticate(self):
        self.client.credentials()

    def authenticate_as(self, role):
        """Swap the client to a fresh user holding ``role``."""
        user = factories.make_user()
        if role:
            grant_role(user, role)
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        return user


class BillingRoleAPITestCase(AuthenticatedAPITestCase):
    role = BILLING_GROUP


class ReadOnlyRoleAPITestCase(AuthenticatedAPITestCase):
    role = READONLY_GROUP
