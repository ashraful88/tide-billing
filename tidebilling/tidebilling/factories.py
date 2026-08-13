"""Object factories shared by the app test suites.

Every helper fills in only the fields the model actually requires, leaving
generated values (``order_number``, ``due_date``, ``total_price``, …) to the
model ``save()`` overrides so tests exercise that logic rather than bypass it.

Named ``factories.py`` rather than ``test_*.py`` so Django's ``test*.py``
discovery pattern does not collect it as a test module.
"""

from decimal import Decimal
from itertools import count

from django.contrib.auth.models import User
from django.utils import timezone

from customers.models import Customer, CustomerContact
from invoices.models import Invoice, InvoiceItem
from orders.models import Order, OrderItem
from payments.models import Payment, Refund, StoredPaymentMethod
from products.models import Category, Product, SubCategory, Tag
from services.models import (
    Service,
    ServiceCategory,
    ServiceDeliverable,
    ServiceFeedback,
    ServiceRequest,
    TimeLog,
)
from subscriptions.models import Subscription, SubscriptionPlan

_seq = count(1)


def unique(prefix='x'):
    """Return a process-unique suffix for fields with a UNIQUE constraint."""
    return f'{prefix}{next(_seq)}'


def make_user(**kwargs):
    kwargs.setdefault('username', unique('user'))
    kwargs.setdefault('password', 'pw')
    return User.objects.create_user(**kwargs)


def make_customer(**kwargs):
    n = next(_seq)
    kwargs.setdefault('cus_id', n)
    kwargs.setdefault('name', f'Customer {n}')
    kwargs.setdefault('email', f'customer{n}@example.com')
    kwargs.setdefault('phone', f'+100000{n:04d}')
    kwargs.setdefault('note', '')
    return Customer.objects.create(**kwargs)


def make_contact(customer=None, **kwargs):
    n = next(_seq)
    kwargs.setdefault('name', f'Contact {n}')
    kwargs.setdefault('email', f'contact{n}@example.com')
    kwargs.setdefault('phone', f'+200000{n:04d}')
    return CustomerContact.objects.create(
        customer=customer or make_customer(), **kwargs
    )


def make_category(**kwargs):
    n = next(_seq)
    kwargs.setdefault('title', f'Category {n}')
    kwargs.setdefault('cat_id', n)
    kwargs.setdefault('slug', f'category-{n}')
    return Category.objects.create(**kwargs)


def make_subcategory(parent=None, **kwargs):
    n = next(_seq)
    kwargs.setdefault('title', f'SubCategory {n}')
    kwargs.setdefault('cat_id', n)
    kwargs.setdefault('slug', f'subcategory-{n}')
    return SubCategory.objects.create(parent=parent or make_category(), **kwargs)


def make_tag(**kwargs):
    kwargs.setdefault('slug', unique('tag-'))
    return Tag.objects.create(**kwargs)


def make_product(**kwargs):
    # base_price/price are DecimalField(max_digits=5) -> hard ceiling of 999.99.
    n = next(_seq)
    kwargs.setdefault('title', f'Product {n}')
    kwargs.setdefault('sku', f'SKU-{n}')
    kwargs.setdefault('slug', f'product-{n}')
    kwargs.setdefault('qty', 100)
    kwargs.setdefault('base_price', Decimal('50.00'))
    kwargs.setdefault('price', Decimal('100.00'))
    kwargs.setdefault('body', 'Description')
    return Product.objects.create(**kwargs)


def make_order(customer=None, **kwargs):
    return Order.objects.create(customer=customer or make_customer(), **kwargs)


def make_order_item(order=None, product=None, **kwargs):
    kwargs.setdefault('quantity', 1)
    return OrderItem.objects.create(
        order=order or make_order(),
        product=product or make_product(),
        **kwargs,
    )


def make_invoice(customer=None, **kwargs):
    return Invoice.objects.create(customer=customer or make_customer(), **kwargs)


def make_invoice_item(invoice=None, **kwargs):
    kwargs.setdefault('description', 'Line item')
    kwargs.setdefault('quantity', Decimal('1'))
    kwargs.setdefault('unit_price', Decimal('100.00'))
    return InvoiceItem.objects.create(invoice=invoice or make_invoice(), **kwargs)


def make_payment(invoice=None, customer=None, **kwargs):
    invoice = invoice or make_invoice()
    kwargs.setdefault('amount', Decimal('100.00'))
    kwargs.setdefault('payment_method', 'credit_card')
    return Payment.objects.create(
        invoice=invoice, customer=customer or invoice.customer, **kwargs
    )


def make_refund(payment=None, **kwargs):
    kwargs.setdefault('amount', Decimal('10.00'))
    kwargs.setdefault('reason', 'Customer request')
    return Refund.objects.create(payment=payment or make_payment(), **kwargs)


def make_payment_method(customer=None, **kwargs):
    kwargs.setdefault('type', 'credit_card')
    return StoredPaymentMethod.objects.create(
        customer=customer or make_customer(), **kwargs
    )


def make_plan(**kwargs):
    n = next(_seq)
    kwargs.setdefault('name', f'Plan {n}')
    kwargs.setdefault('slug', f'plan-{n}')
    kwargs.setdefault('price', Decimal('100.00'))
    return SubscriptionPlan.objects.create(**kwargs)


def make_subscription(customer=None, plan=None, **kwargs):
    return Subscription.objects.create(
        customer=customer or make_customer(),
        plan=plan or make_plan(),
        **kwargs,
    )


def make_service_category(**kwargs):
    n = next(_seq)
    kwargs.setdefault('name', f'Service Category {n}')
    kwargs.setdefault('slug', f'service-category-{n}')
    return ServiceCategory.objects.create(**kwargs)


def make_service(category=None, **kwargs):
    n = next(_seq)
    kwargs.setdefault('name', f'Service {n}')
    kwargs.setdefault('slug', f'service-{n}')
    kwargs.setdefault('description', 'Service description')
    kwargs.setdefault('base_price', Decimal('500.00'))
    return Service.objects.create(
        category=category or make_service_category(), **kwargs
    )


def make_service_request(customer=None, service=None, **kwargs):
    kwargs.setdefault('title', 'Request title')
    kwargs.setdefault('description', 'Request description')
    return ServiceRequest.objects.create(
        customer=customer or make_customer(),
        service=service or make_service(),
        **kwargs,
    )


def make_deliverable(service_request=None, **kwargs):
    kwargs.setdefault('title', 'Deliverable')
    kwargs.setdefault('description', 'Deliverable description')
    return ServiceDeliverable.objects.create(
        service_request=service_request or make_service_request(), **kwargs
    )


def make_time_log(service_request=None, user=None, **kwargs):
    kwargs.setdefault('start_time', timezone.now())
    kwargs.setdefault('description', 'Worked on the request')
    return TimeLog.objects.create(
        service_request=service_request or make_service_request(),
        user=user or make_user(),
        **kwargs,
    )


def make_feedback(service_request=None, **kwargs):
    kwargs.setdefault('overall_rating', 5)
    return ServiceFeedback.objects.create(
        service_request=service_request or make_service_request(), **kwargs
    )
