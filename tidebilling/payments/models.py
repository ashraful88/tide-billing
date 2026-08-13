from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
import uuid

from customers.models import Customer
from invoices.models import Invoice


class PaymentStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    PROCESSING = 'processing', 'Processing'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'
    CANCELLED = 'cancelled', 'Cancelled'
    REFUNDED = 'refunded', 'Refunded'
    PARTIALLY_REFUNDED = 'partially_refunded', 'Partially Refunded'


class PaymentMethod(models.TextChoices):
    CREDIT_CARD = 'credit_card', 'Credit Card'
    DEBIT_CARD = 'debit_card', 'Debit Card'
    BANK_TRANSFER = 'bank_transfer', 'Bank Transfer'
    PAYPAL = 'paypal', 'PayPal'
    STRIPE = 'stripe', 'Stripe'
    CASH = 'cash', 'Cash'
    CHECK = 'check', 'Check'
    CRYPTO = 'crypto', 'Cryptocurrency'
    OTHER = 'other', 'Other'


class PaymentGateway(models.TextChoices):
    STRIPE = 'stripe', 'Stripe'
    PAYPAL = 'paypal', 'PayPal'
    SQUARE = 'square', 'Square'
    RAZORPAY = 'razorpay', 'Razorpay'
    MANUAL = 'manual', 'Manual'


class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_reference = models.CharField(max_length=100, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='payments')
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    
    # Payment details
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    payment_gateway = models.CharField(max_length=20, choices=PaymentGateway.choices, default=PaymentGateway.MANUAL)
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    
    # Gateway specific fields
    gateway_transaction_id = models.CharField(max_length=255, blank=True)
    gateway_response = models.JSONField(blank=True, null=True)
    
    # Timestamps
    payment_date = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    # Additional details
    description = models.TextField(blank=True)
    failure_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['payment_reference']),
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['invoice']),
            models.Index(fields=['payment_date']),
            models.Index(fields=['gateway_transaction_id']),
        ]

    def __str__(self):
        return f"Payment {self.payment_reference} - {self.customer.name} - {self.amount}"

    def save(self, *args, **kwargs):
        if not self.payment_reference:
            # Generate payment reference
            from django.utils import timezone
            now = timezone.now()
            self.payment_reference = f"PAY-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def mark_as_completed(self):
        """Mark payment as completed and update invoice"""
        from django.utils import timezone
        
        self.status = PaymentStatus.COMPLETED
        self.processed_at = timezone.now()
        self.save()
        
        # Update invoice payment status
        self.invoice.paid_amount += self.amount
        if self.invoice.paid_amount >= self.invoice.total_amount:
            self.invoice.mark_as_paid(self.processed_at)
        else:
            self.invoice.status = 'partially_paid'
            self.invoice.save()

    def mark_as_failed(self, reason=None):
        """Mark payment as failed"""
        self.status = PaymentStatus.FAILED
        if reason:
            self.failure_reason = reason
        self.save()


class Refund(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    refund_reference = models.CharField(max_length=100, unique=True)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='refunds')
    
    # Refund details
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    
    # Gateway specific
    gateway_refund_id = models.CharField(max_length=255, blank=True)
    gateway_response = models.JSONField(blank=True, null=True)
    
    # Timestamps
    refund_date = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Refund {self.refund_reference} - {self.amount}"

    def save(self, *args, **kwargs):
        if not self.refund_reference:
            # Generate refund reference
            from django.utils import timezone
            now = timezone.now()
            self.refund_reference = f"REF-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)


class StoredPaymentMethod(models.Model):
    """Stored payment methods for customers"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='payment_methods')
    
    # Payment method details
    type = models.CharField(max_length=20, choices=PaymentMethod.choices)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    # Card details (encrypted/tokenized)
    last_four_digits = models.CharField(max_length=4, blank=True)
    card_brand = models.CharField(max_length=20, blank=True)  # Visa, MasterCard, etc.
    expiry_month = models.PositiveIntegerField(null=True, blank=True)
    expiry_year = models.PositiveIntegerField(null=True, blank=True)
    
    # Gateway tokens
    stripe_payment_method_id = models.CharField(max_length=255, blank=True)
    paypal_payment_method_id = models.CharField(max_length=255, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        if self.last_four_digits:
            return f"{self.card_brand} ending in {self.last_four_digits}"
        return f"{self.type} for {self.customer.name}"

    def save(self, *args, **kwargs):
        # Ensure only one default payment method per customer
        if self.is_default:
            StoredPaymentMethod.objects.filter(
                customer=self.customer, 
                is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)
