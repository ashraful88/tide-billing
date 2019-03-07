from __future__ import unicode_literals
from datetime import timedelta

from django.db import models
from customers.models import Customer
from products.models import Product

class Order_status(models.Model):
    order_status = models.CharField(max_length=30)
    def __str__(self):
        return self.order_status

class Order(models.Model):
    order_id = models.IntegerField(unique=True)
    customer = models.ForeignKey(Customer)
    order_date = models.DateTimeField()
    order_status = models.ForeignKey(Order_status)
    def __str__(self):
        return str(self.order_id)

class Order_item(models.Model):
    order = models.ForeignKey(Order)
    product = models.ForeignKey(Product)
    item_status = models.CharField(max_length=30)
    original_price = models.FloatField()
    price = models.FloatField()
    qty = models.IntegerField(default=1)
    subtotal = models.FloatField()
    tax_amount = models.FloatField(default=0)
    discount_amount = models.FloatField(default=0)
    row_total = models.FloatField()
    renew_duration = models.DurationField(default=0)
    def __str__(self):
        return str(self.id)

class subscription_product(models.Model):
    STATUS_CHOICES = (
    ('ACTIVE', 'Active'),
    ('SUSPENDED', 'Sunpended'),
    ('HOLD', 'Hold'),
    )
    title = models.CharField(max_length=150)
    customer = models.ForeignKey(Customer)
    product = models.ForeignKey(Product)
    requiring_duration = models.DurationField(default=0)
    price = models.FloatField(default=0)
    start_date = models.DateTimeField(auto_now_add=True)
    expiration_date = models.DateTimeField(null=True)
    status = models.CharField(max_length=30,choices=STATUS_CHOICES,default='ACTIVE')
    def __str__(self):
        return self.title

class subscription_order(models.Model):
    STATUS_CHOICES = (
    ('ACTIVE', 'Active'),
    ('SUSPENDED', 'Sunpended'),
    ('HOLD', 'Hold'),
    )
    Order = models.ForeignKey(Order)
    item = models.ForeignKey(Order_item)
    note = models.TextField()
    status = models.CharField(max_length=30,choices=STATUS_CHOICES,default='ACTIVE')

class subscription_flat(models.Model):
    title = models.CharField(max_length=150)
    customer_name = models.CharField(max_length=150)
    product_name = models.CharField(max_length=300)
    order_id = models.CharField(max_length=150)
    order_item_id = models.CharField(max_length=150)
    status = models.CharField(max_length=30)
    requiring_duration = models.DurationField(default=0)
    start_date = models.DateTimeField()
