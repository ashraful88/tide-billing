from django.db import models

from customers.models import Customer
from products.models import Product
from services.models import Services

# Create your models here.
class Order_status(models.Model):
    order_status = models.CharField(max_length=30)
    def __str__(self):
        return self.order_status

class Order(models.Model):
    order_id = models.IntegerField(unique=True)
    customer = models.ForeignKey(Customer.Customer)
    order_date = models.DateTimeField()
    order_status = models.ForeignKey(Order_status)
    def __str__(self):
        return str(self.order_id)

class Order_item_subscription(models.Model):
    STATUS_CHOICES = (
    ('ACTIVE', 'Active'),
    ('SUSPENDED', 'Sunpended'),
    ('HOLD', 'Hold'),
    )
    order = models.ForeignKey(Order)
    service = models.ForeignKey(Services.Service)
    note = models.TextField()
    price = models.FloatField()
    qty = models.IntegerField(default=1)
    subtotal = models.FloatField()
    tax_amount = models.FloatField(default=0)
    discount_amount = models.FloatField(default=0)
    row_total = models.FloatField()
    requiring_duration = models.DurationField(default=0)
    status = models.CharField(max_length=30,choices=STATUS_CHOICES,default='ACTIVE')

class Order_item_product(models.Model):
    order = models.ForeignKey(Order)
    product = models.ForeignKey(Product.Product)
    item_status = models.CharField(max_length=30)
    original_price = models.FloatField()
    price = models.FloatField()
    qty = models.IntegerField(default=1)
    subtotal = models.FloatField()
    tax_amount = models.FloatField(default=0)
    discount_amount = models.FloatField(default=0)
    row_total = models.FloatField()
    def __str__(self):
        return str(self.id)

