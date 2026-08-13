from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
import uuid
from datetime import timedelta
from django.utils import timezone

from customers.models import Customer
from products.models import Product
from tidebilling.money import ZERO, money


class SubscriptionStatus(models.TextChoices):
    ACTIVE = 'active', 'Active'
    INACTIVE = 'inactive', 'Inactive'
    CANCELLED = 'cancelled', 'Cancelled'
    SUSPENDED = 'suspended', 'Suspended'
    PAST_DUE = 'past_due', 'Past Due'
    TRIAL = 'trial', 'Trial'
    EXPIRED = 'expired', 'Expired'


class BillingFrequency(models.TextChoices):
    DAILY = 'daily', 'Daily'
    WEEKLY = 'weekly', 'Weekly'
    MONTHLY = 'monthly', 'Monthly'
    QUARTERLY = 'quarterly', 'Quarterly'
    SEMI_ANNUALLY = 'semi_annually', 'Semi-Annually'
    ANNUALLY = 'annually', 'Annually'


class SubscriptionPlan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    
    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    billing_frequency = models.CharField(max_length=20, choices=BillingFrequency.choices, default=BillingFrequency.MONTHLY)
    
    # Trial settings
    trial_period_days = models.PositiveIntegerField(default=0)
    
    # Features
    features = models.JSONField(default=list, blank=True)  # List of features
    max_users = models.PositiveIntegerField(null=True, blank=True)
    max_storage_gb = models.PositiveIntegerField(null=True, blank=True)
    
    # Settings
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    
    # Gateway IDs
    stripe_price_id = models.CharField(max_length=255, blank=True)
    paypal_plan_id = models.CharField(max_length=255, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['price']

    def __str__(self):
        return f"{self.name} - {self.price}/{self.billing_frequency}"

    @property
    def monthly_price(self):
        """Convert price to monthly equivalent for comparison.

        Multipliers must be Decimal: `Decimal * float` raises TypeError, which
        would surface as a 500 from any endpoint serialising this field.
        """
        frequency_multipliers = {
            BillingFrequency.DAILY: Decimal('30'),
            BillingFrequency.WEEKLY: Decimal('4.33'),
            BillingFrequency.MONTHLY: Decimal('1'),
            BillingFrequency.QUARTERLY: Decimal('1') / Decimal('3'),
            BillingFrequency.SEMI_ANNUALLY: Decimal('1') / Decimal('6'),
            BillingFrequency.ANNUALLY: Decimal('1') / Decimal('12'),
        }
        multiplier = frequency_multipliers.get(
            self.billing_frequency, Decimal('1')
        )
        return self.price * multiplier


class Subscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription_number = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='subscriptions')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT)
    
    # Status and dates
    status = models.CharField(max_length=20, choices=SubscriptionStatus.choices, default=SubscriptionStatus.ACTIVE)
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(null=True, blank=True)
    trial_end_date = models.DateTimeField(null=True, blank=True)
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    next_billing_date = models.DateTimeField()
    
    # Pricing (can be different from plan if custom pricing)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    
    # Payment and cancellation
    payment_method = models.ForeignKey('payments.StoredPaymentMethod', on_delete=models.SET_NULL, null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    
    # Gateway IDs
    stripe_subscription_id = models.CharField(max_length=255, blank=True)
    paypal_subscription_id = models.CharField(max_length=255, blank=True)
    
    # Usage tracking
    usage_limits = models.JSONField(default=dict, blank=True)  # Custom usage limits
    current_usage = models.JSONField(default=dict, blank=True)  # Current usage
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['subscription_number']),
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['next_billing_date']),
            models.Index(fields=['current_period_end']),
        ]

    def __str__(self):
        return f"Subscription {self.subscription_number} - {self.customer.name}"

    def save(self, *args, **kwargs):
        if not self.subscription_number:
            # Generate subscription number
            now = timezone.now()
            self.subscription_number = f"SUB-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        
        if not self.price:
            self.price = self.plan.price
        
        if not self.current_period_start:
            self.current_period_start = self.start_date
        
        if not self.current_period_end or not self.next_billing_date:
            self.calculate_billing_dates()
        
        super().save(*args, **kwargs)

    def calculate_billing_dates(self):
        """Calculate billing dates based on frequency"""
        frequency_days = {
            BillingFrequency.DAILY: 1,
            BillingFrequency.WEEKLY: 7,
            BillingFrequency.MONTHLY: 30,
            BillingFrequency.QUARTERLY: 90,
            BillingFrequency.SEMI_ANNUALLY: 180,
            BillingFrequency.ANNUALLY: 365,
        }
        
        days = frequency_days.get(self.plan.billing_frequency, 30)
        
        if not self.current_period_end:
            self.current_period_end = self.current_period_start + timedelta(days=days)
        
        if not self.next_billing_date:
            self.next_billing_date = self.current_period_end

    def is_in_trial(self):
        """Check if subscription is in trial period"""
        if not self.trial_end_date:
            return False
        return timezone.now() < self.trial_end_date

    def cancel(self, reason=None, at_period_end=True):
        """Cancel subscription"""
        self.cancel_at_period_end = at_period_end
        self.cancelled_at = timezone.now()
        if reason:
            self.cancellation_reason = reason
        
        if not at_period_end:
            self.status = SubscriptionStatus.CANCELLED
            self.end_date = timezone.now()
        
        self.save()

    def reactivate(self):
        """Reactivate a cancelled subscription"""
        if self.status == SubscriptionStatus.CANCELLED:
            self.status = SubscriptionStatus.ACTIVE
            self.cancel_at_period_end = False
            self.cancelled_at = None
            self.end_date = None
            self.save()

    def unused_period_fraction(self, at=None):
        """Fraction of the current billing period still unused, as a Decimal.

        Returns 0 outside the period rather than a negative value, so callers
        never produce a proration that charges backwards.
        """
        at = at or timezone.now()
        period = self.current_period_end - self.current_period_start
        total_seconds = Decimal(str(period.total_seconds()))
        if total_seconds <= 0:
            return ZERO
        remaining = Decimal(str((self.current_period_end - at).total_seconds()))
        if remaining <= 0:
            return ZERO
        return min(Decimal('1'), remaining / total_seconds)

    def change_plan(self, new_plan, user=None, prorate=True, reason=''):
        """Move to a new plan, recording proration for the unused period.

        The customer is credited for the unused remainder of the plan they are
        leaving and charged pro rata for the plan they are joining. The net
        figure lands on the SubscriptionChange row so the next invoice can pick
        it up; the billing period itself is deliberately left intact.
        """
        old_plan = self.plan
        # Capture the old price before reassigning it, otherwise the audit row
        # records the new price in both columns.
        old_price = money(self.price)
        new_price = money(new_plan.price)

        proration = ZERO
        if prorate:
            fraction = self.unused_period_fraction()
            credit = money(old_price * fraction)
            charge = money(new_price * fraction)
            proration = money(charge - credit)

        if new_plan.monthly_price > old_plan.monthly_price:
            change_type = 'plan_upgrade'
        elif new_plan.monthly_price < old_plan.monthly_price:
            change_type = 'plan_downgrade'
        else:
            change_type = 'price_change'

        self.plan = new_plan
        self.price = new_price
        self.save()

        return SubscriptionChange.objects.create(
            subscription=self,
            change_type=change_type,
            old_plan=old_plan,
            new_plan=new_plan,
            old_price=old_price,
            new_price=new_price,
            proration_amount=proration,
            reason=reason,
            created_by=user,
        )

    def upgrade_plan(self, new_plan, user=None, prorate=True):
        """Backwards-compatible alias for change_plan."""
        return self.change_plan(new_plan, user=user, prorate=prorate)

    def expire_if_period_ended(self, at=None):
        """Complete a cancel-at-period-end request once the period is over.

        Without this the flag was set and then never acted on: the renewal task
        skipped these subscriptions, so they simply stayed ACTIVE forever.
        """
        at = at or timezone.now()
        if not self.cancel_at_period_end:
            return False
        if self.status != SubscriptionStatus.ACTIVE:
            return False
        if self.current_period_end > at:
            return False

        self.status = SubscriptionStatus.CANCELLED
        self.end_date = self.current_period_end
        self.save()
        return True


    def add_usage(self, metric, amount):
        """Add usage for a specific metric"""
        if metric not in self.current_usage:
            self.current_usage[metric] = 0
        self.current_usage[metric] += amount
        self.save()


class SubscriptionChange(models.Model):
    """Track subscription changes"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='changes')
    
    change_type = models.CharField(max_length=50, choices=[
        ('plan_upgrade', 'Plan Upgrade'),
        ('plan_downgrade', 'Plan Downgrade'),
        ('price_change', 'Price Change'),
        ('status_change', 'Status Change'),
        ('cancellation', 'Cancellation'),
        ('reactivation', 'Reactivation'),
    ])
    
    # Plan changes
    old_plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='old_changes')
    new_plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='new_changes')
    
    # Price changes
    old_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    new_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # Net proration for the unused remainder of the period: positive means the
    # customer owes the difference, negative means they are owed a credit.
    proration_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0.00')
    )
    # Cleared once the amount has been carried onto a renewal invoice, so a
    # mid-period change is billed exactly once.
    proration_invoiced = models.BooleanField(default=False)
    
    # Status changes
    old_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20, blank=True)
    
    # Details
    reason = models.TextField(blank=True)
    effective_date = models.DateTimeField(default=timezone.now)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.subscription.subscription_number} - {self.change_type}"


class SubscriptionUsage(models.Model):
    """Track subscription usage metrics"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='usage_records')
    
    metric_name = models.CharField(max_length=100)  # e.g., 'api_calls', 'storage_gb', 'users'
    usage_amount = models.DecimalField(max_digits=15, decimal_places=2)
    billing_period_start = models.DateTimeField()
    billing_period_end = models.DateTimeField()
    
    # Metadata
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['subscription', 'metric_name', 'billing_period_start']
        ordering = ['-recorded_at']

    def __str__(self):
        return f"{self.subscription.subscription_number} - {self.metric_name}: {self.usage_amount}"
