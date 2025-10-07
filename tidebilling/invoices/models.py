from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
import uuid
from datetime import timedelta
from django.utils import timezone

from customers.models import Customer
from orders.models import Order


class InvoiceStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    SENT = 'sent', 'Sent'
    PAID = 'paid', 'Paid'
    PARTIALLY_PAID = 'partially_paid', 'Partially Paid'
    OVERDUE = 'overdue', 'Overdue'
    CANCELLED = 'cancelled', 'Cancelled'
    REFUNDED = 'refunded', 'Refunded'


class InvoiceType(models.TextChoices):
    STANDARD = 'standard', 'Standard'
    RECURRING = 'recurring', 'Recurring'
    CREDIT_NOTE = 'credit_note', 'Credit Note'
    DEBIT_NOTE = 'debit_note', 'Debit Note'


class PaymentTerms(models.TextChoices):
    NET_15 = 'net_15', 'Net 15 days'
    NET_30 = 'net_30', 'Net 30 days'
    NET_45 = 'net_45', 'Net 45 days'
    NET_60 = 'net_60', 'Net 60 days'
    DUE_ON_RECEIPT = 'due_on_receipt', 'Due on Receipt'


class Invoice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='invoices')
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='invoices', null=True, blank=True)
    
    # Invoice details
    invoice_type = models.CharField(max_length=20, choices=InvoiceType.choices, default=InvoiceType.STANDARD)
    status = models.CharField(max_length=20, choices=InvoiceStatus.choices, default=InvoiceStatus.DRAFT)
    
    # Dates
    issue_date = models.DateField(default=timezone.now)
    due_date = models.DateField()
    sent_date = models.DateTimeField(null=True, blank=True)
    paid_date = models.DateTimeField(null=True, blank=True)
    
    # Payment terms
    payment_terms = models.CharField(max_length=20, choices=PaymentTerms.choices, default=PaymentTerms.NET_30)
    
    # Amounts
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    outstanding_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    # Additional details
    notes = models.TextField(blank=True)
    terms_and_conditions = models.TextField(blank=True)
    footer_text = models.TextField(blank=True)
    
    # Recurring invoice details
    is_recurring = models.BooleanField(default=False)
    recurring_frequency = models.CharField(max_length=20, blank=True, 
                                         choices=[
                                             ('weekly', 'Weekly'),
                                             ('monthly', 'Monthly'),
                                             ('quarterly', 'Quarterly'),
                                             ('yearly', 'Yearly')
                                         ])
    next_invoice_date = models.DateField(null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['invoice_number']),
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['due_date']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.customer.name}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            # Generate invoice number
            from django.utils import timezone
            now = timezone.now()
            self.invoice_number = f"INV-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        
        if not self.due_date and self.issue_date:
            # Set due date based on payment terms
            days_map = {
                PaymentTerms.NET_15: 15,
                PaymentTerms.NET_30: 30,
                PaymentTerms.NET_45: 45,
                PaymentTerms.NET_60: 60,
                PaymentTerms.DUE_ON_RECEIPT: 0,
            }
            days = days_map.get(self.payment_terms, 30)
            self.due_date = self.issue_date + timedelta(days=days)
        
        self.outstanding_amount = self.total_amount - self.paid_amount
        super().save(*args, **kwargs)

    def calculate_totals(self):
        """Calculate invoice totals based on invoice items"""
        items = self.items.all()
        self.subtotal = sum(item.total_price for item in items)
        self.tax_amount = self.subtotal * Decimal('0.10')  # 10% tax
        self.total_amount = self.subtotal + self.tax_amount - self.discount_amount
        self.outstanding_amount = self.total_amount - self.paid_amount
        self.save()

    @property
    def is_overdue(self):
        """Check if invoice is overdue"""
        if self.status in [InvoiceStatus.PAID, InvoiceStatus.CANCELLED]:
            return False
        return timezone.now().date() > self.due_date

    def mark_as_sent(self):
        """Mark invoice as sent"""
        self.status = InvoiceStatus.SENT
        self.sent_date = timezone.now()
        self.save()

    def mark_as_paid(self, payment_date=None):
        """Mark invoice as fully paid"""
        self.status = InvoiceStatus.PAID
        self.paid_date = payment_date or timezone.now()
        self.paid_amount = self.total_amount
        self.outstanding_amount = Decimal('0.00')
        self.save()


class InvoiceItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Optional product reference
    product = models.ForeignKey('products.Product', on_delete=models.SET_NULL, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.description} x {self.quantity}"

    def save(self, *args, **kwargs):
        self.total_price = self.unit_price * self.quantity
        super().save(*args, **kwargs)


class InvoiceHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='history')
    status_from = models.CharField(max_length=20, choices=InvoiceStatus.choices)
    status_to = models.CharField(max_length=20, choices=InvoiceStatus.choices)
    notes = models.TextField(blank=True)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-changed_at']

    def __str__(self):
        return f"Invoice {self.invoice.invoice_number}: {self.status_from} → {self.status_to}"
