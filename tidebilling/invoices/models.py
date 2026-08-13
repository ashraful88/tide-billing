from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.contrib.auth.models import User
from decimal import Decimal
import uuid
from datetime import timedelta
from django.utils import timezone

from customers.models import Customer
from orders.models import Order
from tidebilling.money import ZERO, apply_tax, default_currency, default_tax_rate, money

from .numbering import CREDIT_NOTE_PREFIX, INVOICE_PREFIX, allocate


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


# Statuses after which the document is legally issued and its figures are
# frozen. Corrections are made by cancelling or issuing a credit note.
FINALIZED_STATUSES = frozenset(
    {
        InvoiceStatus.SENT,
        InvoiceStatus.PAID,
        InvoiceStatus.PARTIALLY_PAID,
        InvoiceStatus.OVERDUE,
        InvoiceStatus.CANCELLED,
        InvoiceStatus.REFUNDED,
    }
)


class InvoiceFinalizedError(ValidationError):
    """Raised when an issued invoice is edited instead of credit-noted."""


class Invoice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(max_length=50, unique=True, editable=False)
    # PROTECT: financial records must survive an attempt to delete the party
    # they belong to. Customers are archived instead (see Customer.archive).
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='invoices')
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='invoices', null=True, blank=True)

    # Invoice details
    invoice_type = models.CharField(max_length=20, choices=InvoiceType.choices, default=InvoiceType.STANDARD)
    status = models.CharField(max_length=20, choices=InvoiceStatus.choices, default=InvoiceStatus.DRAFT)

    # A credit note refers back to the invoice it corrects.
    original_invoice = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='credit_notes',
    )

    # Dates
    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField()
    sent_date = models.DateTimeField(null=True, blank=True)
    paid_date = models.DateTimeField(null=True, blank=True)

    # Payment terms
    payment_terms = models.CharField(max_length=20, choices=PaymentTerms.choices, default=PaymentTerms.NET_30)

    # Amounts. currency and tax_rate are snapshotted at issue time so a later
    # change to settings does not retroactively alter issued documents.
    currency = models.CharField(max_length=3, default=default_currency)
    tax_rate = models.DecimalField(max_digits=6, decimal_places=4, default=default_tax_rate)
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

    # Dunning state. Without these the reminder task can only ever fire once
    # per invoice, because it filters on the status it just changed.
    reminder_count = models.PositiveIntegerField(default=0)
    last_reminder_at = models.DateTimeField(null=True, blank=True)

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
        constraints = [
            models.CheckConstraint(
                condition=models.Q(subtotal__gte=0)
                & models.Q(tax_amount__gte=0)
                & models.Q(discount_amount__gte=0)
                & models.Q(total_amount__gte=0)
                & models.Q(paid_amount__gte=0),
                name='invoice_amounts_non_negative',
            ),
        ]

    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.customer.name}"

    @property
    def is_finalized(self):
        """True once the document has been issued and its figures are frozen."""
        return self.status in FINALIZED_STATUSES

    def _number_prefix(self):
        if self.invoice_type == InvoiceType.CREDIT_NOTE:
            return CREDIT_NOTE_PREFIX
        return INVOICE_PREFIX

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self.invoice_number:
                # Allocated inside the same transaction as the INSERT so a
                # rollback returns the number to the sequence.
                self.invoice_number = allocate(
                    self._number_prefix(), self.issue_date.year
                )

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

            self.outstanding_amount = money(self.total_amount) - money(self.paid_amount)
            super().save(*args, **kwargs)

    def calculate_totals(self):
        """Recalculate totals from invoice items.

        Refuses to run on an issued document: rewriting the figures on a sent
        or paid invoice is what credit notes exist to avoid.
        """
        if self.is_finalized:
            raise InvoiceFinalizedError(
                f'Invoice {self.invoice_number} is {self.status} and cannot be '
                f'recalculated. Issue a credit note instead.'
            )

        items = self.items.all()
        self.subtotal = money(sum((item.total_price for item in items), ZERO))
        self.tax_amount = apply_tax(self.subtotal, self.tax_rate)
        self.total_amount = money(
            self.subtotal + self.tax_amount - money(self.discount_amount)
        )
        self.outstanding_amount = money(self.total_amount - money(self.paid_amount))
        self.save()

    @property
    def is_overdue(self):
        """Check if invoice is overdue"""
        if self.status in [InvoiceStatus.PAID, InvoiceStatus.CANCELLED]:
            return False
        return timezone.localdate() > self.due_date

    def record_status_change(self, old_status, new_status, notes='', user=None):
        """Append an audit row. Called by every status transition."""
        if old_status == new_status:
            return None
        return InvoiceHistory.objects.create(
            invoice=self,
            status_from=old_status,
            status_to=new_status,
            notes=notes,
            changed_by=user,
        )

    def set_status(self, new_status, notes='', user=None, save=True):
        """Transition status and write the audit row in one step."""
        old_status = self.status
        self.status = new_status
        if save:
            self.save()
        self.record_status_change(old_status, new_status, notes, user)

    def mark_as_sent(self, user=None):
        """Mark invoice as sent"""
        old_status = self.status
        self.status = InvoiceStatus.SENT
        self.sent_date = timezone.now()
        self.save()
        self.record_status_change(old_status, self.status, 'Invoice sent', user)

    def mark_as_paid(self, payment_date=None, user=None):
        """Mark invoice as fully paid"""
        old_status = self.status
        self.status = InvoiceStatus.PAID
        self.paid_date = payment_date or timezone.now()
        self.paid_amount = money(self.total_amount)
        self.outstanding_amount = ZERO
        self.save()
        self.record_status_change(old_status, self.status, 'Invoice paid', user)

    @transaction.atomic
    def create_credit_note(self, amount=None, reason='', user=None):
        """Issue a credit note against this invoice.

        The original is left untouched — that is the point of a credit note.
        The note carries positive amounts and its own sequential number from
        the CRN series.
        """
        if self.invoice_type == InvoiceType.CREDIT_NOTE:
            raise ValidationError('Cannot credit-note a credit note.')

        amount = money(amount if amount is not None else self.total_amount)
        if amount <= ZERO:
            raise ValidationError('Credit note amount must be positive.')
        already_credited = money(
            sum(
                (note.total_amount for note in self.credit_notes.all()),
                ZERO,
            )
        )
        if already_credited + amount > money(self.total_amount):
            raise ValidationError(
                'Credit notes would exceed the invoice total '
                f'({already_credited} already credited of {self.total_amount}).'
            )

        note = Invoice.objects.create(
            customer=self.customer,
            order=self.order,
            invoice_type=InvoiceType.CREDIT_NOTE,
            original_invoice=self,
            status=InvoiceStatus.DRAFT,
            currency=self.currency,
            tax_rate=self.tax_rate,
            subtotal=amount,
            total_amount=amount,
            payment_terms=self.payment_terms,
            notes=reason,
            created_by=user,
        )
        self.record_status_change(
            self.status,
            self.status,
            f'Credit note {note.invoice_number} issued for {amount}',
            user,
        )
        return note


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

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.description} x {self.quantity}"

    def save(self, *args, **kwargs):
        self.total_price = money(money(self.unit_price) * Decimal(str(self.quantity)))
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
        verbose_name_plural = 'Invoice history'

    def __str__(self):
        return f"Invoice {self.invoice.invoice_number}: {self.status_from} → {self.status_to}"
