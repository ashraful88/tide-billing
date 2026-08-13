from celery import shared_task
from django.contrib.sessions.models import Session
from django.utils import timezone

from tidebilling.money import money


@shared_task
def cleanup_expired_sessions():
    """Clean up expired sessions"""
    try:
        expired_sessions = Session.objects.filter(expire_date__lt=timezone.now())
        count = expired_sessions.count()
        expired_sessions.delete()
        print(f"Cleaned up {count} expired sessions")
        return count
    except Exception as e:
        print(f"Error cleaning up sessions: {str(e)}")
        return 0


@shared_task
def generate_monthly_reports():
    """Generate monthly billing reports"""
    from datetime import datetime, timedelta
    from django.db.models import Sum
    from invoices.models import Invoice
    from payments.models import Payment
    
    try:
        # Calculate date range for last month
        today = datetime.now().date()
        first_day_this_month = today.replace(day=1)
        last_day_last_month = first_day_this_month - timedelta(days=1)
        first_day_last_month = last_day_last_month.replace(day=1)
        
        # Calculate metrics
        total_invoiced = Invoice.objects.filter(
            created_at__date__range=[first_day_last_month, last_day_last_month]
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        
        total_paid = Payment.objects.filter(
            payment_date__date__range=[first_day_last_month, last_day_last_month],
            status='completed'
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        print(f"Monthly Report - Invoiced: {total_invoiced}, Paid: {total_paid}")

        # Serialised as strings, not floats: float() on a money Decimal
        # reintroduces binary rounding error into the figures being reported.
        return {
            'period': f"{first_day_last_month} to {last_day_last_month}",
            'total_invoiced': str(money(total_invoiced)),
            'total_paid': str(money(total_paid)),
            'total_outstanding': str(money(total_invoiced - total_paid)),
        }
        
    except Exception as e:
        print(f"Error generating monthly report: {str(e)}")
        return None


@shared_task
def backup_database():
    """Create database backup (placeholder)"""
    # This would typically use pg_dump or similar
    # For now, just log the action
    print(f"Database backup initiated at {timezone.now()}")
    return True


@shared_task
def send_system_health_check():
    """Send system health check email to admins"""
    from django.core.mail import mail_admins
    from django.db import connection
    
    try:
        # Check database connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            db_status = "OK"
    except Exception as e:
        db_status = f"ERROR: {str(e)}"
    
    # Check other system components here
    
    health_report = f"""
    System Health Check Report
    =========================
    Timestamp: {timezone.now()}
    Database: {db_status}
    
    System is {'healthy' if db_status == 'OK' else 'experiencing issues'}.
    """
    
    mail_admins(
        'System Health Check',
        health_report,
        fail_silently=False
    )
    
    return db_status == "OK"