"""Role-based permissions.

The system is staff-only: there are no customer logins. Access is granted by
Django group membership, provisioned by the ``setup_roles`` management command.

    ADMIN    full access, including deletes and archiving customers
    BILLING  day-to-day work: create/edit orders, invoices, payments, refunds
    READONLY reporting only

Superusers bypass every check. A user in no role group gets read-only access,
so an account that exists but has not been provisioned cannot mutate billing
data.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

ADMIN_GROUP = 'admin'
BILLING_GROUP = 'billing'
READONLY_GROUP = 'readonly'

ALL_ROLE_GROUPS = (ADMIN_GROUP, BILLING_GROUP, READONLY_GROUP)


def _in_group(user, name):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=name).exists()


def is_admin(user):
    return _in_group(user, ADMIN_GROUP)


def is_billing_staff(user):
    return is_admin(user) or _in_group(user, BILLING_GROUP)


class IsAdmin(BasePermission):
    """Admin-only. Used for destructive and configuration endpoints."""

    message = 'This action requires the admin role.'

    def has_permission(self, request, view):
        return is_admin(request.user)


class IsBillingStaffOrReadOnly(BasePermission):
    """Read for any authenticated user; write for billing staff and admins.

    Deletes are additionally restricted to admins: billing clerks correct
    mistakes by cancelling or issuing a credit note, not by removing records.
    """

    message = 'This action requires the billing or admin role.'

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        if request.method == 'DELETE':
            return is_admin(user)
        return is_billing_staff(user)
