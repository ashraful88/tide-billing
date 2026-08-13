from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
import uuid

from customers.models import Customer
from products.models import Product


class OrderStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    CONFIRMED = 'confirmed', 'Confirmed'
    PROCESSING = 'processing', 'Processing'
    SHIPPED = 'shipped', 'Shipped'
    DELIVERED = 'delivered', 'Delivered'
    CANCELLED = 'cancelled', 'Cancelled'
    REFUNDED = 'refunded', 'Refunded'


class OrderType(models.TextChoices):
    ONE_TIME = 'one_time', 'One Time'
    SUBSCRIPTION = 'subscription', 'Subscription'
    RECURRING = 'recurring', 'Recurring'


class Order(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='orders')
    order_type = models.CharField(max_length=20, choices=OrderType.choices, default=OrderType.ONE_TIME)
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    
    # Pricing
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    shipping_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    # Additional info
    notes = models.TextField(blank=True)
    shipping_address = models.TextField(blank=True)
    billing_address = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order_number']),
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Order {self.order_number} - {self.customer.name}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            # Generate order number
            from django.utils import timezone
            now = timezone.now()
            self.order_number = f"ORD-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def calculate_totals(self):
        """Calculate order totals based on order items"""
        items = self.items.all()
        self.subtotal = sum(item.total_price for item in items)
        self.tax_amount = self.subtotal * Decimal('0.10')  # 10% tax
        self.total_amount = self.subtotal + self.tax_amount + self.shipping_amount - self.discount_amount
        self.save()


class OrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Product snapshot (in case product details change)
    product_name = models.CharField(max_length=200)
    product_sku = models.CharField(max_length=100)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['order', 'product']

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"

    def save(self, *args, **kwargs):
        if not self.unit_price:
            self.unit_price = self.product.price
        if not self.product_name:
            self.product_name = self.product.title
        if not self.product_sku:
            self.product_sku = self.product.sku
        self.total_price = self.unit_price * self.quantity
        super().save(*args, **kwargs)


class OrderHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='history')
    status_from = models.CharField(max_length=20, choices=OrderStatus.choices)
    status_to = models.CharField(max_length=20, choices=OrderStatus.choices)
    notes = models.TextField(blank=True)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-changed_at']

    def __str__(self):
        return f"Order {self.order.order_number}: {self.status_from} → {self.status_to}"
