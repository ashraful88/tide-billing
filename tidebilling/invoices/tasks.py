from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from .models import Invoice, InvoiceStatus


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
    
    for invoice in recurring_invoices:
        try:
            # Create new invoice based on the recurring one
            new_invoice = Invoice.objects.create(
                customer=invoice.customer,
                invoice_type=invoice.invoice_type,
                subtotal=invoice.subtotal,
                tax_amount=invoice.tax_amount,
                discount_amount=invoice.discount_amount,
                total_amount=invoice.total_amount,
                payment_terms=invoice.payment_terms,
                notes=invoice.notes,
                terms_and_conditions=invoice.terms_and_conditions,
                footer_text=invoice.footer_text,
                is_recurring=True,
                recurring_frequency=invoice.recurring_frequency,
            )
            
            # Copy invoice items
            for item in invoice.items.all():
                new_invoice.items.create(
                    description=item.description,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    product=item.product
                )
            
            # Update next invoice date
            frequency_days = {
                'weekly': 7,
                'monthly': 30,
                'quarterly': 90,
                'yearly': 365
            }
            days = frequency_days.get(invoice.recurring_frequency, 30)
            invoice.next_invoice_date = invoice.next_invoice_date + timedelta(days=days)
            invoice.save()
            
        except Exception as e:
            print(f"Error processing recurring invoice {invoice.id}: {str(e)}")


@shared_task
def send_invoice_reminders():
    """Send reminders for overdue invoices"""
    from django.template.loader import render_to_string
    
    # Get overdue invoices
    overdue_invoices = Invoice.objects.filter(
        due_date__lt=timezone.now().date(),
        status__in=[InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID]
    )
    
    for invoice in overdue_invoices:
        try:
            # Send reminder email
            subject = f"Payment Reminder - Invoice {invoice.invoice_number}"
            message = f"""
            Dear {invoice.customer.name},
            
            This is a friendly reminder that invoice {invoice.invoice_number} 
            for ${invoice.outstanding_amount} is now overdue.
            
            Due Date: {invoice.due_date}
            Amount Due: ${invoice.outstanding_amount}
            
            Please make payment at your earliest convenience.
            
            Best regards,
            Your Billing Team
            """
            
            send_mail(
                subject,
                message,
                'noreply@tidebilling.com',
                [invoice.customer.email],
                fail_silently=False,
            )
            
            # Update invoice status to overdue
            if invoice.status != InvoiceStatus.OVERDUE:
                invoice.status = InvoiceStatus.OVERDUE
                invoice.save()
                
        except Exception as e:
            print(f"Error sending reminder for invoice {invoice.id}: {str(e)}")


@shared_task
def generate_invoice_from_order(order_id):
    """Generate invoice from order"""
    from orders.models import Order
    
    try:
        order = Order.objects.get(id=order_id)
        
        # Create invoice
        invoice = Invoice.objects.create(
            customer=order.customer,
            order=order,
            subtotal=order.subtotal,
            tax_amount=order.tax_amount,
            discount_amount=order.discount_amount,
            total_amount=order.total_amount,
        )
        
        # Create invoice items from order items
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
    """Send invoice via email"""
    try:
        invoice = Invoice.objects.get(id=invoice_id)
        
        subject = f"Invoice {invoice.invoice_number}"
        message = f"""
        Dear {invoice.customer.name},
        
        Please find attached your invoice {invoice.invoice_number}.
        
        Invoice Details:
        - Amount: ${invoice.total_amount}
        - Due Date: {invoice.due_date}
        
        Thank you for your business!
        
        Best regards,
        Your Team
        """
        
        send_mail(
            subject,
            message,
            'invoices@tidebilling.com',
            [invoice.customer.email],
            fail_silently=False,
        )
        
        # Mark invoice as sent
        invoice.mark_as_sent()
        
        return True
        
    except Exception as e:
        print(f"Error sending invoice email {invoice_id}: {str(e)}")
        return False