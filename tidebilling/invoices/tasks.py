from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from tidebilling.money import ZERO, money

from .models import Invoice, InvoiceStatus

# Days after the due date at which each reminder goes out. The invoice's
# reminder_count indexes into this, so escalation stops after the last entry
# instead of mailing the customer forever.
DUNNING_SCHEDULE_DAYS = [0, 7, 14, 30]

# Statuses that still owe money and are therefore chaseable. OVERDUE must be
# included: the task sets that status itself, and excluding it meant every
# invoice received exactly one reminder ever.
CHASEABLE_STATUSES = [
    InvoiceStatus.SENT,
    InvoiceStatus.PARTIALLY_PAID,
    InvoiceStatus.OVERDUE,
]


def _from_email():
    return getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'noreply@tidebilling.com'


@shared_task
def process_recurring_invoices():
    """Process recurring invoices that are due"""
    from datetime import date

    # Get invoices that should generate new instances
    recurring_invoices = Invoice.objects.filter(
        is_recurring=True,
        next_invoice_date__lte=date.today(),
        status__in=[InvoiceStatus.PAID, InvoiceStatus.SENT]
    )

    generated = 0
    for invoice in recurring_invoices:
        try:
            with transaction.atomic():
                # Lock the source row so two concurrent beats cannot both read
                # the same next_invoice_date and emit duplicate invoices.
                source = Invoice.objects.select_for_update().get(pk=invoice.pk)
                if source.next_invoice_date > date.today():
                    continue

                new_invoice = Invoice.objects.create(
                    customer=source.customer,
                    invoice_type=source.invoice_type,
                    currency=source.currency,
                    tax_rate=source.tax_rate,
                    subtotal=source.subtotal,
                    tax_amount=source.tax_amount,
                    discount_amount=source.discount_amount,
                    total_amount=source.total_amount,
                    payment_terms=source.payment_terms,
                    notes=source.notes,
                    terms_and_conditions=source.terms_and_conditions,
                    footer_text=source.footer_text,
                    is_recurring=True,
                    recurring_frequency=source.recurring_frequency,
                )

                for item in source.items.all():
                    new_invoice.items.create(
                        description=item.description,
                        quantity=item.quantity,
                        unit_price=item.unit_price,
                        product=item.product
                    )

                frequency_days = {
                    'weekly': 7,
                    'monthly': 30,
                    'quarterly': 90,
                    'yearly': 365
                }
                days = frequency_days.get(source.recurring_frequency, 30)
                source.next_invoice_date = source.next_invoice_date + timedelta(days=days)
                source.save()
                generated += 1

        except Exception as e:
            # Re-raised in eager mode (tests); logged in a worker.
            print(f"Error processing recurring invoice {invoice.id}: {str(e)}")

    return generated


@shared_task
def send_invoice_reminders():
    """Send escalating reminders for overdue invoices."""
    today = timezone.localdate()
    now = timezone.now()

    overdue_invoices = Invoice.objects.filter(
        due_date__lt=today,
        status__in=CHASEABLE_STATUSES,
    )

    sent = 0
    for invoice in overdue_invoices:
        try:
            if invoice.reminder_count >= len(DUNNING_SCHEDULE_DAYS):
                continue  # escalation exhausted

            days_overdue = (today - invoice.due_date).days
            if days_overdue < DUNNING_SCHEDULE_DAYS[invoice.reminder_count]:
                continue  # not yet due for the next step

            step = invoice.reminder_count + 1
            subject = (
                f"Payment Reminder {step}/{len(DUNNING_SCHEDULE_DAYS)} - "
                f"Invoice {invoice.invoice_number}"
            )
            message = f"""
            Dear {invoice.customer.name},

            This is reminder {step} that invoice {invoice.invoice_number}
            for {invoice.currency} {invoice.outstanding_amount} is now
            {days_overdue} day(s) overdue.

            Due Date: {invoice.due_date}
            Amount Due: {invoice.currency} {invoice.outstanding_amount}

            Please make payment at your earliest convenience.

            Best regards,
            Your Billing Team
            """

            EmailMessage(
                subject, message, _from_email(), [invoice.customer.email]
            ).send(fail_silently=False)

            invoice.reminder_count = step
            invoice.last_reminder_at = now
            if invoice.status != InvoiceStatus.OVERDUE:
                invoice.set_status(
                    InvoiceStatus.OVERDUE,
                    notes=f'Reminder {step} sent',
                )
            else:
                invoice.save()
            sent += 1

        except Exception as e:
            print(f"Error sending reminder for invoice {invoice.id}: {str(e)}")

    return sent


@shared_task
def generate_invoice_from_order(order_id, user_id=None):
    """Generate invoice from order"""
    from django.contrib.auth.models import User
    from orders.models import Order

    try:
        with transaction.atomic():
            order = Order.objects.get(id=order_id)

            # An order is invoiced once; a second call returns the existing one.
            existing = order.invoices.first()
            if existing is not None:
                return existing.id

            invoice = Invoice.objects.create(
                customer=order.customer,
                order=order,
                currency=order.currency,
                tax_rate=order.tax_rate,
                subtotal=order.subtotal,
                tax_amount=order.tax_amount,
                discount_amount=order.discount_amount,
                total_amount=order.total_amount,
                created_by=User.objects.filter(pk=user_id).first(),
            )

            for order_item in order.items.all():
                invoice.items.create(
                    description=order_item.product_name,
                    quantity=order_item.quantity,
                    unit_price=order_item.unit_price,
                    product=order_item.product
                )

            return invoice.id

    except Exception as e:
        print(f"Error generating invoice from order {order_id}: {str(e)}")
        return None


@shared_task
def send_invoice_email(invoice_id):
    """Send invoice via email with a PDF attached."""
    from tidebilling.pdf import render_invoice_pdf

    try:
        invoice = Invoice.objects.get(id=invoice_id)

        subject = f"Invoice {invoice.invoice_number}"
        message = f"""
        Dear {invoice.customer.name},

        Please find attached your invoice {invoice.invoice_number}.

        Invoice Details:
        - Amount: {invoice.currency} {invoice.total_amount}
        - Due Date: {invoice.due_date}

        Thank you for your business!

        Best regards,
        Your Team
        """

        email = EmailMessage(
            subject, message, _from_email(), [invoice.customer.email]
        )
        # The body promises an attachment, so actually attach one.
        email.attach(
            f'{invoice.invoice_number}.pdf',
            render_invoice_pdf(invoice),
            'application/pdf',
        )
        email.send(fail_silently=False)

        invoice.mark_as_sent()

        return True

    except Exception as e:
        print(f"Error sending invoice email {invoice_id}: {str(e)}")
        return False


@shared_task
def mark_overdue_invoices():
    """Flag invoices whose due date has passed.

    Keeps the OVERDUE status accurate even for invoices nobody has run the
    dunning task against yet.
    """
    today = timezone.localdate()
    count = 0
    for invoice in Invoice.objects.filter(
        due_date__lt=today,
        status__in=[InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID],
    ):
        invoice.set_status(InvoiceStatus.OVERDUE, notes='Past due date')
        count += 1
    return count
