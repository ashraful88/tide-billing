"""Provision the admin/billing/readonly role groups.

Idempotent: safe to run on every deploy. Model permissions are attached so the
Django admin honours the same roles as the API.
"""

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

from tidebilling.permissions import ADMIN_GROUP, BILLING_GROUP, READONLY_GROUP

# Apps whose models billing staff may create/change.
BILLING_APPS = [
    'customers',
    'products',
    'orders',
    'invoices',
    'payments',
    'subscriptions',
    'services',
]


class Command(BaseCommand):
    help = 'Create the admin, billing and readonly role groups.'

    def handle(self, *args, **options):
        perms = Permission.objects.filter(
            content_type__app_label__in=BILLING_APPS
        ).select_related('content_type')

        view_perms = [p for p in perms if p.codename.startswith('view_')]
        write_perms = [
            p
            for p in perms
            if p.codename.split('_')[0] in ('add', 'change', 'view')
        ]

        matrix = {
            ADMIN_GROUP: list(perms),
            BILLING_GROUP: write_perms,
            READONLY_GROUP: view_perms,
        }

        for name, group_perms in matrix.items():
            group, created = Group.objects.get_or_create(name=name)
            group.permissions.set(group_perms)
            self.stdout.write(
                self.style.SUCCESS(
                    f'{"Created" if created else "Updated"} group '
                    f'{name!r} with {len(group_perms)} permissions'
                )
            )
