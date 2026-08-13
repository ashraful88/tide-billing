from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.contrib.auth.models import User
from decimal import Decimal
import uuid

from customers.models import Customer
from invoices.models import Invoice, InvoiceStatus
from tidebilling.money import ZERO, money


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


class PaymentStateError(ValidationError):
    """Raised when a payment transition is attempted from the wrong state."""


class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_reference = models.CharField(max_length=100, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='payments')
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='payments')

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
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name='payment_amount_positive',
            ),
        ]

    def __str__(self):
        return f"Payment {self.payment_reference} - {self.customer.name} - {self.amount}"

    def clean(self):
        super().clean()
        if self.invoice_id and self.currency != self.invoice.currency:
            raise ValidationError(
                {
                    'currency': (
                        f'Payment currency {self.currency} does not match '
                        f'invoice currency {self.invoice.currency}.'
                    )
                }
            )

    def save(self, *args, **kwargs):
        if not self.payment_reference:
            from django.utils import timezone
            now = timezone.now()
            self.payment_reference = f"PAY-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    @property
    def refunded_amount(self):
        """Total already refunded against this payment."""
        return money(
            sum(
                (
                    refund.amount
                    for refund in self.refunds.all()
                    if refund.status == PaymentStatus.COMPLETED
                ),
                ZERO,
            )
        )

    @property
    def refundable_amount(self):
        return money(self.amount) - self.refunded_amount

    @transaction.atomic
    def mark_as_completed(self, user=None):
        """Record the payment against its invoice.

        Idempotent by state: only a pending payment may complete, so a repeated
        call cannot double-credit the invoice. The invoice row is locked for
        the update because two clerks recording cash against the same invoice
        would otherwise both read the old paid_amount and one write would win.
        """
        from django.utils import timezone

        if self.status != PaymentStatus.PENDING:
            raise PaymentStateError(
                f'Payment {self.payment_reference} is {self.status}; only '
                f'pending payments can be completed.'
            )

        self.status = PaymentStatus.COMPLETED
        self.processed_at = timezone.now()
        if user is not None:
            self.processed_by = user
        self.save()

        invoice = Invoice.objects.select_for_update().get(pk=self.invoice_id)
        invoice.paid_amount = money(invoice.paid_amount) + money(self.amount)

        if invoice.paid_amount >= money(invoice.total_amount):
            invoice.mark_as_paid(self.processed_at, user=user)
        else:
            invoice.set_status(
                InvoiceStatus.PARTIALLY_PAID,
                notes=f'Payment {self.payment_reference} recorded',
                user=user,
            )
        return self

    def mark_as_failed(self, reason=None, user=None):
        """Mark payment as failed"""
        if self.status == PaymentStatus.COMPLETED:
            raise PaymentStateError(
                f'Payment {self.payment_reference} is already completed and '
                f'cannot be failed. Issue a refund instead.'
            )
        self.status = PaymentStatus.FAILED
        if reason:
            self.failure_reason = reason
        if user is not None:
            self.processed_by = user
        self.save()
        return self


class Refund(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    refund_reference = models.CharField(max_length=100, unique=True, editable=False)
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name='refunds')

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
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name='refund_amount_positive',
            ),
        ]

    def __str__(self):
        return f"Refund {self.refund_reference} - {self.amount}"

    def clean(self):
        super().clean()
        if not self.payment_id:
            return
        # Guard the cumulative total, not just this row: three refunds of the
        # full payment amount each used to be accepted.
        already = money(
            sum(
                (
                    other.amount
                    for other in self.payment.refunds.exclude(pk=self.pk)
                    if other.status
                    in (PaymentStatus.COMPLETED, PaymentStatus.PENDING)
                ),
                ZERO,
            )
        )
        if already + money(self.amount) > money(self.payment.amount):
            raise ValidationError(
                {
                    'amount': (
                        f'Refunds would exceed the payment: {already} already '
                        f'refunded of {self.payment.amount}.'
                    )
                }
            )

    def save(self, *args, **kwargs):
        if not self.refund_reference:
            from django.utils import timezone
            now = timezone.now()
            self.refund_reference = f"REF-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    @transaction.atomic
    def mark_as_completed(self, user=None):
        """Settle the refund against the payment and its invoice.

        This is what makes a Refund more than a note: it reduces the invoice's
        paid amount, reopens the outstanding balance and moves the payment to
        (partially) refunded.
        """
        from django.utils import timezone

        if self.status == PaymentStatus.COMPLETED:
            raise PaymentStateError(
                f'Refund {self.refund_reference} is already completed.'
            )

        payment = Payment.objects.select_for_update().get(pk=self.payment_id)
        # A partially refunded payment is still refundable up to its total;
        # only the cumulative cap in clean() limits how much.
        if payment.status not in (
            PaymentStatus.COMPLETED,
            PaymentStatus.PARTIALLY_REFUNDED,
        ):
            raise PaymentStateError(
                'Only a completed payment can be refunded.'
            )

        self.status = PaymentStatus.COMPLETED
        self.processed_at = timezone.now()
        if user is not None:
            self.processed_by = user
        self.save()

        invoice = Invoice.objects.select_for_update().get(pk=payment.invoice_id)
        invoice.paid_amount = max(
            ZERO, money(invoice.paid_amount) - money(self.amount)
        )
        invoice.outstanding_amount = money(invoice.total_amount) - invoice.paid_amount

        if invoice.paid_amount <= ZERO:
            new_status = InvoiceStatus.REFUNDED
        elif invoice.paid_amount < money(invoice.total_amount):
            new_status = InvoiceStatus.PARTIALLY_PAID
        else:
            new_status = invoice.status
        invoice.paid_date = None if invoice.paid_amount <= ZERO else invoice.paid_date
        invoice.set_status(
            new_status,
            notes=f'Refund {self.refund_reference} of {self.amount} applied',
            user=user,
        )

        # Refresh from the locked row so refunded_amount includes this refund.
        payment.refresh_from_db()
        payment.status = (
            PaymentStatus.REFUNDED
            if payment.refunded_amount >= money(payment.amount)
            else PaymentStatus.PARTIALLY_REFUNDED
        )
        payment.save()
        return self


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
