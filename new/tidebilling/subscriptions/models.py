from django.db import models
import uuid

from customers.models import Customer
from orders.models import Order
from services.models import Service

# Create your models here.
class Subscription(models.Model):
    STATUS_CHOICES = (
    ('ACTIVE', 'Active'),
    ('SUSPENDED', 'Sunpended'),
    ('HOLD', 'Hold'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=150)
    customer = models.ForeignKey(Customer.Customer)
    service = models.ForeignKey(Service.Service)
    requiring_duration = models.DurationField(default=0)
    price = models.FloatField(default=0)
    start_date = models.DateTimeField(auto_now_add=True)
    expiration_date = models.DateTimeField(null=True)
    status = models.CharField(max_length=30,choices=STATUS_CHOICES,default='ACTIVE')
    def __str__(self):
        return self.title

class subscription_flat(models.Model):
    title = models.CharField(max_length=150)
    customer_name = models.CharField(max_length=150)
    product_name = models.CharField(max_length=300)
    order_id = models.CharField(max_length=150)
    order_item_id = models.CharField(max_length=150)
    status = models.CharField(max_length=30)
    requiring_duration = models.DurationField(default=0)
    start_date = models.DateTimeField()
