from django.db import models
import uuid

from customers.models import Customer
from services.models import Service

# Create your models here.
class Subscription_plans(models.Model):
    STATUS_CHOICES = (
    ('ACTIVE', 'Active'),
    ('SUSPENDED', 'Sunpended'),
    ('HOLD', 'Hold'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=150)
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    requiring_duration = models.DurationField(default=0)
    price = models.FloatField(default=0)
    start_date = models.DateTimeField(auto_now_add=True)
    expiration_date = models.DateTimeField(null=True)
    status = models.CharField(max_length=30,choices=STATUS_CHOICES,default='ACTIVE')

    def __str__(self):
        return self.title

    def __unicode__(self):
        return self.title
        
    class Meta:
        verbose_name = "Subscription Plan"
        verbose_name_plural = "Subscription Plans"

# customer will subscrive here first, then order->payment will be initiated        
class Subscription(models.Model):
    STATUS_CHOICES = (
    ('ACTIVE', 'Active'),
    ('SUSPENDED', 'Sunpended'),
    ('CANCELLED', 'Cancelled'),
    ('HOLD', 'Hold'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=150)
    plan = models.ForeignKey(Subscription_plans, on_delete=models.DO_NOTHING)
    customer = models.ForeignKey(Customer, on_delete=models.DO_NOTHING)
    service = models.ForeignKey(Service, on_delete=models.DO_NOTHING)
    requiring_duration = models.DurationField(default=0)
    price = models.FloatField(default=0)
    start_date = models.DateTimeField(auto_now_add=True)
    expiration_date = models.DateTimeField(null=True)
    status = models.CharField(max_length=30,choices=STATUS_CHOICES,default='ACTIVE')
    
    def __str__(self):
        return self.title
    
    def __unicode__(self):
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
    
    def __str__(self):
        return self.title
    
    def __unicode__(self):
        return self.title