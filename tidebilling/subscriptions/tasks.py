from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from tidebilling.money import ZERO, apply_tax, default_tax_rate, money

from .models import Subscription, SubscriptionStatus

FREQUENCY_DAYS = {
    'daily': 1,
    'weekly': 7,
    'monthly': 30,
    'quarterly': 90,
    'semi_annually': 180,
    'annually': 365,
}


def _from_email():
    return getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'noreply@tidebilling.com'


def _overage_lines(subscription):
    """Return (description, amount) for each metric over its limit.

    Usage was previously tracked and warned about but never billed.
    ``usage_limits`` may carry a plain number (limit only) or a mapping with a
    ``unit_price`` so the overage can be charged.
    """
    lines = []
    for metric, limit in (subscription.usage_limits or {}).items():
        unit_price = ZERO
        if isinstance(limit, dict):
            unit_price = money(limit.get('unit_price', 0))
            limit_value = Decimal(str(limit.get('limit', 0)))
        else:
            limit_value = Decimal(str(limit))

        used = Decimal(str((subscription.current_usage or {}).get(metric, 0)))
        excess = used - limit_value
        if excess > 0 and unit_price > ZERO:
            lines.append(
                (
                    f'{metric} overage: {excess} x {unit_price}',
                    money(excess * unit_price),
                )
            )
    return lines


@shared_task
def process_subscription_renewals():
    """Process subscription renewals"""
    renewals_due = Subscription.objects.filter(
        next_billing_date__lte=timezone.now(),
        status=SubscriptionStatus.ACTIVE,
        cancel_at_period_end=False
    )

    renewed = 0
    for subscription in renewals_due:
        try:
            with transaction.atomic():
                # Lock so two beats cannot renew the same subscription twice.
                sub = Subscription.objects.select_for_update().get(
                    pk=subscription.pk
                )
                if sub.next_billing_date > timezone.now():
                    continue

                days = FREQUENCY_DAYS.get(sub.plan.billing_frequency, 30)

                overages = _overage_lines(sub)
                # Unbilled proration recorded by any plan change this period.
                proration = money(
                    sum(
                        (
                            change.proration_amount
                            for change in sub.changes.filter(
                                proration_invoiced=False
                            )
                        ),
                        ZERO,
                    )
                )

                period_start = sub.current_period_start
                period_end = sub.current_period_end

                sub.current_period_start = sub.current_period_end
                sub.current_period_end = sub.current_period_end + timedelta(days=days)
                sub.next_billing_date = sub.current_period_end
                sub.current_usage = {}
                sub.save()

                _create_renewal_invoice(sub, overages, proration, period_start, period_end)
                sub.changes.filter(proration_invoiced=False).update(
                    proration_invoiced=True
                )
                renewed += 1

        except Exception as e:
            print(f"Error processing subscription renewal {subscription.id}: {str(e)}")

    return renewed


def _create_renewal_invoice(subscription, overages, proration, period_start, period_end):
    """Build the renewal invoice, including overage and proration lines."""
    from invoices.models import Invoice

    invoice = Invoice.objects.create(
        customer=subscription.customer,
        invoice_type='recurring',
        currency=subscription.currency,
        tax_rate=default_tax_rate(),
        notes=(
            f'Subscription renewal for {subscription.plan.name} '
            f'({period_start:%Y-%m-%d} to {period_end:%Y-%m-%d})'
        ),
    )

    invoice.items.create(
        description=f'{subscription.plan.name} subscription',
        quantity=Decimal('1'),
        unit_price=money(subscription.price),
    )
    for description, amount in overages:
        invoice.items.create(
            description=description,
            quantity=Decimal('1'),
            unit_price=amount,
        )
    if proration != ZERO:
        invoice.items.create(
            description='Proration adjustment for mid-period plan change',
            quantity=Decimal('1'),
            unit_price=proration,
        )

    invoice.calculate_totals()
    return invoice


@shared_task
def expire_period_end_cancellations():
    """Cancel subscriptions whose cancel-at-period-end date has passed.

    Without this the flag was recorded and never acted on, leaving cancelled
    subscriptions ACTIVE indefinitely.
    """
    candidates = Subscription.objects.filter(
        cancel_at_period_end=True,
        status=SubscriptionStatus.ACTIVE,
        current_period_end__lte=timezone.now(),
    )

    expired = 0
    for subscription in candidates:
        try:
            if subscription.expire_if_period_ended():
                expired += 1
                send_mail(
                    'Subscription Cancelled',
                    f'Your subscription for {subscription.plan.name} has ended.',
                    _from_email(),
                    [subscription.customer.email],
                    fail_silently=True,
                )
        except Exception as e:
            print(f"Error expiring subscription {subscription.id}: {str(e)}")

    return expired


@shared_task
def check_trial_expirations():
    """Check and process trial expirations"""
    expired_trials = Subscription.objects.filter(
        trial_end_date__lte=timezone.now(),
        status=SubscriptionStatus.TRIAL
    )

    converted = 0
    for subscription in expired_trials:
        try:
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.save()

            send_mail(
                'Trial Period Ended',
                f'Your trial for {subscription.plan.name} has ended. Your subscription is now active.',
                _from_email(),
                [subscription.customer.email],
                fail_silently=False,
            )
            converted += 1

        except Exception as e:
            print(f"Error processing trial expiration {subscription.id}: {str(e)}")

    return converted


@shared_task
def send_subscription_expiry_warnings():
    """Send warnings for expiring subscriptions"""
    warning_date = timezone.now() + timedelta(days=7)
    expiring_subscriptions = Subscription.objects.filter(
        current_period_end__lte=warning_date,
        status=SubscriptionStatus.ACTIVE,
        cancel_at_period_end=True
    )

    sent = 0
    for subscription in expiring_subscriptions:
        try:
            send_mail(
                'Subscription Expiring Soon',
                f'Your subscription for {subscription.plan.name} will expire on {subscription.current_period_end}.',
                _from_email(),
                [subscription.customer.email],
                fail_silently=False,
            )
            sent += 1

        except Exception as e:
            print(f"Error sending expiry warning {subscription.id}: {str(e)}")

    return sent


@shared_task
def update_subscription_usage(subscription_id, metric, amount):
    """Update subscription usage"""
    try:
        subscription = Subscription.objects.get(id=subscription_id)
        subscription.add_usage(metric, amount)

        usage_limits = subscription.usage_limits or {}
        current_usage = subscription.current_usage or {}

        for metric_name, limit in usage_limits.items():
            limit_value = (
                limit.get('limit', 0) if isinstance(limit, dict) else limit
            )
            if Decimal(str(current_usage.get(metric_name, 0))) > Decimal(str(limit_value)):
                send_mail(
                    'Usage Limit Exceeded',
                    f'Your usage for {metric_name} has exceeded the limit of {limit_value}.',
                    _from_email(),
                    [subscription.customer.email],
                    fail_silently=False,
                )

        return True

    except Exception as e:
        print(f"Error updating subscription usage {subscription_id}: {str(e)}")
        return False
