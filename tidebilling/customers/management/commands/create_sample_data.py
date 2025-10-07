from django.core.management.base import BaseCommand
from django.utils import timezone
from customers.models import Customer
from invoices.models import Invoice
from orders.models import Order
from payments.models import Payment
from subscriptions.models import Subscription


class Command(BaseCommand):
    help = 'Generate sample data for testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--customers',
            type=int,
            default=10,
            help='Number of customers to create',
        )
        parser.add_argument(
            '--orders',
            type=int,
            default=20,
            help='Number of orders to create',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Creating sample data...'))
        
        # Create customers
        customers_count = options['customers']
        for i in range(customers_count):
            Customer.objects.create(
                cus_id=1000 + i,
                name=f'Test Customer {i+1}',
                email=f'customer{i+1}@example.com',
                phone=f'+1234567{i:04d}',
                note=f'Sample customer {i+1}'
            )
        
        self.stdout.write(
            self.style.SUCCESS(f'Created {customers_count} customers')
        )
        
        # Create orders
        orders_count = options['orders']
        customers = Customer.objects.all()
        
        for i in range(orders_count):
            customer = customers[i % len(customers)]
            Order.objects.create(
                customer=customer,
                order_type='one_time',
                status='pending',
                subtotal=100.00,
                tax_amount=10.00,
                total_amount=110.00
            )
        
        self.stdout.write(
            self.style.SUCCESS(f'Created {orders_count} orders')
        )
        
        self.stdout.write(
            self.style.SUCCESS('Sample data creation completed!')
        )