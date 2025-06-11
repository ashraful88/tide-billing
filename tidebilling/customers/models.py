from __future__ import unicode_literals
from django.db import models

import uuid


class Customer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cus_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=200)
    email = models.CharField(max_length=200, unique=True)
    phone = models.CharField(max_length=200)
    landline = models.CharField(max_length=200, blank=True)
    note = models.TextField()
    #slug = models.SlugField(max_length=200, unique=True)
    status = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    def __str__(self):
        return self.name


class CustomerContact(models.Model):
    id =  models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    email = models.CharField(max_length=200, unique=True)
    phone = models.CharField(max_length=200, unique=True)
    homephone = models.CharField(max_length=200, blank=True)
    landline = models.CharField(max_length=200, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    def __str__(self):
        return self.name
    
