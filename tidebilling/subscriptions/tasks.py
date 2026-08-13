from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone
from datetime import timedelta

from .models import Subscription, SubscriptionStatus


@shared_task
def process_subscription_renewals():
    """Process subscription renewals"""
    # Get subscriptions that need renewal
    renewals_due = Subscription.objects.filter(
        next_billing_date__lte=timezone.now(),
        status=SubscriptionStatus.ACTIVE,
        cancel_at_period_end=False
    )
    
    for subscription in renewals_due:
        try:
            # Process renewal logic here
            # This would typically integrate with payment processors
            
            # For now, just update the billing dates
            frequency_days = {
                'daily': 1,
                'weekly': 7,
                'monthly': 30,
                'quarterly': 90,
                'semi_annually': 180,
                'annually': 365,
            }
            
            days = frequency_days.get(subscription.plan.billing_frequency, 30)
            
            # Update billing period
            subscription.current_period_start = subscription.current_period_end
            subscription.current_period_end = subscription.current_period_end + timedelta(days=days)
            subscription.next_billing_date = subscription.current_period_end
            
            # Reset usage if applicable
            subscription.current_usage = {}
            
            subscription.save()
            
            # Create invoice for the renewal
            from invoices.models import Invoice
            Invoice.objects.create(
                customer=subscription.customer,
                invoice_type='recurring',
                subtotal=subscription.price,
                tax_amount=subscription.price * 0.1,  # 10% tax
                total_amount=subscription.price * 1.1,
                notes=f"Subscription renewal for {subscription.plan.name}"
            )
            
        except Exception as e:
            print(f"Error processing subscription renewal {subscription.id}: {str(e)}")


@shared_task
def check_trial_expirations():
    """Check and process trial expirations"""
    expired_trials = Subscription.objects.filter(
        trial_end_date__lte=timezone.now(),
        status=SubscriptionStatus.TRIAL
    )
    
    for subscription in expired_trials:
        try:
            # Convert trial to active subscription
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.save()
            
            # Send notification email
            send_mail(
                'Trial Period Ended',
                f'Your trial for {subscription.plan.name} has ended. Your subscription is now active.',
                'noreply@tidebilling.com',
                [subscription.customer.email],
                fail_silently=False,
            )
            
        except Exception as e:
            print(f"Error processing trial expiration {subscription.id}: {str(e)}")


@shared_task
def send_subscription_expiry_warnings():
    """Send warnings for expiring subscriptions"""
    # Get subscriptions expiring in 7 days
    warning_date = timezone.now() + timedelta(days=7)
    expiring_subscriptions = Subscription.objects.filter(
        current_period_end__lte=warning_date,
        status=SubscriptionStatus.ACTIVE,
        cancel_at_period_end=True
    )
    
    for subscription in expiring_subscriptions:
        try:
            send_mail(
                'Subscription Expiring Soon',
                f'Your subscription for {subscription.plan.name} will expire on {subscription.current_period_end}.',
                'noreply@tidebilling.com',
                [subscription.customer.email],
                fail_silently=False,
            )
            
        except Exception as e:
            print(f"Error sending expiry warning {subscription.id}: {str(e)}")


@shared_task
def update_subscription_usage(subscription_id, metric, amount):
    """Update subscription usage"""
    try:
        subscription = Subscription.objects.get(id=subscription_id)
        subscription.add_usage(metric, amount)
        
        # Check if usage limits are exceeded
        usage_limits = subscription.usage_limits
        current_usage = subscription.current_usage
        
        for metric_name, limit in usage_limits.items():
            if current_usage.get(metric_name, 0) > limit:
                # Send notification or take action
                send_mail(
                    'Usage Limit Exceeded',
                    f'Your usage for {metric_name} has exceeded the limit of {limit}.',
                    'noreply@tidebilling.com',
                    [subscription.customer.email],
                    fail_silently=False,
                )
                
        return True
        
    except Exception as e:
        print(f"Error updating subscription usage {subscription_id}: {str(e)}")
        return False