from __future__ import unicode_literals
from django.db import models

import uuid


class Customer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    email = models.CharField(max_length=200, unique=True)
    phone = models.CharField(max_length=200)
    note = models.TextField()
    slug = models.SlugField(max_length=200, unique=True)
    status = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    def __str__(self):
        return self.name
#todo: add contact model to add multiple contacts of a customer
