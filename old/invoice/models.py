from __future__ import unicode_literals

from django.db import models
from customers.models import Customer
from orders.models import subscription_product
from orders.models import Order

class Invoice(models.Model):
    invoice_number = models.CharField(max_length=300, unique=True)
    title = models.CharField(max_length=300)
    due_date = models.DateTimeField()
    customer = models.ForeignKey(Customer)
    subscription = models.ForeignKey(subscription_product, null=True, blank=True, default=None)
    order = models.ForeignKey(Order, null=True, blank=True, default=None)
    description = models.TextField()
    status = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    def __str__(self):
        return str(self.invoice_number)
