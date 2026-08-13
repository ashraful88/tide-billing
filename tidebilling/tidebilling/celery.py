import os
from celery import Celery
from django.conf import settings

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tidebilling.settings')

app = Celery('tidebilling')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Celery beat schedule for recurring tasks
app.conf.beat_schedule = {
    'process-recurring-invoices': {
        'task': 'invoices.tasks.process_recurring_invoices',
        'schedule': 3600.0,  # Run every hour
    },
    'send-invoice-reminders': {
        'task': 'invoices.tasks.send_invoice_reminders',
        'schedule': 86400.0,  # Run daily
    },
    'mark-overdue-invoices': {
        'task': 'invoices.tasks.mark_overdue_invoices',
        'schedule': 86400.0,  # Run daily
    },
    'process-subscription-renewals': {
        'task': 'subscriptions.tasks.process_subscription_renewals',
        'schedule': 3600.0,  # Run every hour
    },
    # These three existed as tasks but were never scheduled, so trials never
    # converted and period-end cancellations never completed.
    'check-trial-expirations': {
        'task': 'subscriptions.tasks.check_trial_expirations',
        'schedule': 3600.0,  # Run every hour
    },
    'expire-period-end-cancellations': {
        'task': 'subscriptions.tasks.expire_period_end_cancellations',
        'schedule': 3600.0,  # Run every hour
    },
    'send-subscription-expiry-warnings': {
        'task': 'subscriptions.tasks.send_subscription_expiry_warnings',
        'schedule': 86400.0,  # Run daily
    },
    'cleanup-expired-sessions': {
        'task': 'tidebilling.tasks.cleanup_expired_sessions',
        'schedule': 86400.0,  # Run daily
    },
}

app.conf.timezone = 'UTC'

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')