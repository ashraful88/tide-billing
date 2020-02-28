from datetime import tzinfo, timedelta, datetime
from django.core.management.base import BaseCommand, CommandError
from orders.models import subscription_product
from invoice.models import Invoice

#python manage.py reminder 2016-11-10
class Command(BaseCommand):
    help = 'Check for invoices of subscriptions'

    def add_arguments(self, parser):
        parser.add_argument('run_date', nargs='+', type=str)

    def handle(self, *args, **options):
        for run_date in options['run_date']:
            self.stdout.write(self.style.SUCCESS('Date: "%s"' % datetime.strptime(run_date, "%Y-%m-%d")))
            active_invoices = Invoice.objects.filter(status = True)
            for inv_item in active_invoices:
                now = datetime.now()
                self.stdout.write(self.style.SUCCESS('Invoice: "%s"' % inv_item.title))
