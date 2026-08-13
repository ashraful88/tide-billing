from __future__ import unicode_literals
from django.db import models
from django.utils import timezone

import uuid


class CustomerQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_archived=False)

    def archived(self):
        return self.filter(is_archived=True)


class Customer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cus_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=200)
    email = models.EmailField(max_length=200, unique=True)
    phone = models.CharField(max_length=200)
    landline = models.CharField(max_length=200, blank=True)
    note = models.TextField(blank=True)
    #slug = models.SlugField(max_length=200, unique=True)
    status = models.BooleanField(default=True)

    # Soft delete. Invoices and payments reference customers with PROTECT, so a
    # customer with financial history cannot be deleted; archiving retires them
    # without destroying the audit trail.
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    objects = CustomerQuerySet.as_manager()

    def __str__(self):
        return self.name

    def archive(self):
        """Retire the customer without destroying their financial history."""
        self.is_archived = True
        self.archived_at = timezone.now()
        self.status = False
        self.save(update_fields=['is_archived', 'archived_at', 'status', 'modified'])

    def unarchive(self):
        self.is_archived = False
        self.archived_at = None
        self.status = True
        self.save(update_fields=['is_archived', 'archived_at', 'status', 'modified'])


class CustomerContact(models.Model):
    id =  models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    email = models.EmailField(max_length=200, unique=True)
    phone = models.CharField(max_length=200, unique=True)
    homephone = models.CharField(max_length=200, blank=True)
    landline = models.CharField(max_length=200, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    def __str__(self):
        return self.name
