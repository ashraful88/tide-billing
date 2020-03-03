from django.db import models
import uuid

from customers.models import Customer
from products.models import Product
from subscriptions.models import Subscription

# Create your models here.
class Order_status(models.Model):
    order_status = models.CharField(max_length=30)
    def __str__(self):
        return self.order_status

class Order(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_id = models.IntegerField(unique=True, default=1000)
    customer = models.ForeignKey(Customer, on_delete=models.DO_NOTHING)
    order_date = models.DateTimeField()
    order_status = models.ForeignKey(Order_status, on_delete=models.DO_NOTHING)
    def __str__(self):
        return str(self.order_id)
    def __unicode__(self):
        return str(self.order_id)

class Order_item_subscription(models.Model):
    STATUS_CHOICES = (
    ('ACTIVE', 'Active'),
    ('SUSPENDED', 'Sunpended'),
    ('HOLD', 'Hold'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    subscription = models.ForeignKey(Subscription, on_delete=models.DO_NOTHING)
    note = models.TextField()
    price = models.FloatField()
    qty = models.IntegerField(default=1)
    subtotal = models.FloatField()
    tax_amount = models.FloatField(default=0)
    discount_amount = models.FloatField(default=0)
    row_total = models.FloatField()
    requiring_duration = models.DurationField(default=0)
    status = models.CharField(max_length=30,choices=STATUS_CHOICES,default='ACTIVE')
    
    def __str__(self):
        return self.subscription

    def __unicode__(self):
        return self.subscription

class Order_item_product(models.Model):
    STATUS_CHOICES = (
    ('PROCESSING', 'Processing'),
    ('DELIVERED', 'Delivered'),
    ('HOLD', 'Hold'),
    ('CANCELED', 'Canceled'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.DO_NOTHING)
    original_price = models.FloatField()
    price = models.FloatField()
    qty = models.IntegerField(default=1)
    subtotal = models.FloatField()
    tax_amount = models.FloatField(default=0)
    discount_amount = models.FloatField(default=0)
    row_total = models.FloatField()
    status = models.CharField(max_length=30,choices=STATUS_CHOICES,default='PROCESSING')
    def __str__(self):
        return self.product

    def __unicode__(self):
        return self.product    
    

