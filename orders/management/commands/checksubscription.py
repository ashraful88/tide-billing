from datetime import tzinfo, timedelta, datetime
from django.core.management.base import BaseCommand, CommandError
from orders.models import subscription_product
from invoice.models import Invoice

#python manage.py checksubscription 2016-11-10
class Command(BaseCommand):
    help = 'Check for expiry of subscriptions'

    def add_arguments(self, parser):
        parser.add_argument('run_date', nargs='+', type=str)

    def handle(self, *args, **options):
        for run_date in options['run_date']:
            self.stdout.write(self.style.SUCCESS('Date: "%s"' % datetime.strptime(run_date, "%Y-%m-%d")))
            scn_products = subscription_product.objects.filter(expiration_date__lte = datetime.strptime(run_date, "%Y-%m-%d"))
            for scn_item in scn_products:
                now = datetime.now()
                inv_num = now.strftime("%d%m%Y%S%M%H%f")
                inv = Invoice(invoice_number = inv_num, title = scn_item.title, due_date = scn_item.expiration_date, customer = scn_item.customer, subscription = scn_item, description = scn_item.title, status = True)
                inv.save()
                self.stdout.write(self.style.SUCCESS('Invoice: "%s"' % inv_num))
                self.stdout.write(self.style.SUCCESS('Subscription: "%s"' % scn_item.title))
