import re
from decimal import Decimal

from django.db import IntegrityError
from django.urls import reverse

from orders.models import Order, OrderHistory, OrderItem, OrderStatus, OrderType
from tidebilling import factories
from tidebilling.apitest import AuthenticatedAPITestCase


class OrderModelTests(AuthenticatedAPITestCase):
    def test_order_number_generated_on_first_save(self):
        order = factories.make_order()

        self.assertRegex(order.order_number, r'^ORD-\d{8}-[0-9A-F]{8}$')

    def test_order_number_is_stable_across_saves(self):
        order = factories.make_order()
        original = order.order_number

        order.notes = 'changed'
        order.save()

        order.refresh_from_db()
        self.assertEqual(order.order_number, original)

    def test_order_numbers_are_unique(self):
        numbers = {factories.make_order().order_number for _ in range(10)}

        self.assertEqual(len(numbers), 10)

    def test_defaults(self):
        order = factories.make_order()

        self.assertEqual(order.status, OrderStatus.PENDING)
        self.assertEqual(order.order_type, OrderType.ONE_TIME)
        self.assertEqual(order.total_amount, Decimal('0.00'))

    def test_str(self):
        customer = factories.make_customer(name='Acme')
        order = factories.make_order(customer=customer)

        self.assertEqual(str(order), f'Order {order.order_number} - Acme')

    def test_ordering_is_newest_first(self):
        first = factories.make_order()
        second = factories.make_order()

        self.assertEqual(list(Order.objects.all()), [second, first])


class OrderItemModelTests(AuthenticatedAPITestCase):
    def test_snapshot_fields_copied_from_product(self):
        product = factories.make_product(
            title='Snapshot', sku='SNAP-1', price=Decimal('25.00')
        )
        item = factories.make_order_item(product=product, quantity=2)

        self.assertEqual(item.unit_price, Decimal('25.00'))
        self.assertEqual(item.product_name, 'Snapshot')
        self.assertEqual(item.product_sku, 'SNAP-1')

    def test_total_price_is_derived(self):
        item = factories.make_order_item(
            quantity=3, unit_price=Decimal('10.00')
        )

        self.assertEqual(item.total_price, Decimal('30.00'))

    def test_total_price_recalculated_on_update(self):
        item = factories.make_order_item(
            quantity=1, unit_price=Decimal('10.00')
        )

        item.quantity = 5
        item.save()

        self.assertEqual(item.total_price, Decimal('50.00'))

    def test_snapshot_survives_later_product_change(self):
        product = factories.make_product(title='Original', price=Decimal('10.00'))
        item = factories.make_order_item(product=product)

        product.title = 'Renamed'
        product.price = Decimal('99.00')
        product.save()

        item.refresh_from_db()
        self.assertEqual(item.product_name, 'Original')
        self.assertEqual(item.unit_price, Decimal('10.00'))

    def test_same_product_cannot_be_added_twice(self):
        order = factories.make_order()
        product = factories.make_product()
        factories.make_order_item(order=order, product=product)

        with self.assertRaises(IntegrityError):
            factories.make_order_item(order=order, product=product)

    def test_str(self):
        item = factories.make_order_item(
            product=factories.make_product(title='Thing'), quantity=4
        )

        self.assertEqual(str(item), 'Thing x 4')


class OrderTotalsTests(AuthenticatedAPITestCase):
    def test_totals_sum_items_and_apply_tax(self):
        order = factories.make_order()
        factories.make_order_item(
            order=order, quantity=2, unit_price=Decimal('100.00')
        )
        factories.make_order_item(
            order=order, quantity=1, unit_price=Decimal('50.00')
        )

        order.calculate_totals()

        self.assertEqual(order.subtotal, Decimal('250.00'))
        self.assertEqual(order.tax_amount, Decimal('25.00'))
        self.assertEqual(order.total_amount, Decimal('275.00'))

    def test_totals_include_shipping_and_discount(self):
        order = factories.make_order(
            shipping_amount=Decimal('15.00'),
            discount_amount=Decimal('5.00'),
        )
        factories.make_order_item(
            order=order, quantity=1, unit_price=Decimal('100.00')
        )

        order.calculate_totals()

        # Tax applies to the discounted subtotal: (100 - 5) = 95 taxable,
        # + 9.50 tax + 15 shipping. Taxing before the discount would have
        # charged tax on money the customer never pays.
        self.assertEqual(order.tax_amount, Decimal('9.50'))
        self.assertEqual(order.total_amount, Decimal('119.50'))

    def test_totals_are_zero_with_no_items(self):
        order = factories.make_order()

        order.calculate_totals()

        self.assertEqual(order.subtotal, 0)
        self.assertEqual(order.total_amount, Decimal('0.00'))

    def test_saving_an_item_does_not_recalculate_the_order(self):
        """Totals are recomputed only by an explicit calculate_totals() call."""
        order = factories.make_order()
        factories.make_order_item(
            order=order, quantity=1, unit_price=Decimal('100.00')
        )

        order.refresh_from_db()
        self.assertEqual(order.total_amount, Decimal('0.00'))


class OrderAPITests(AuthenticatedAPITestCase):
    def test_requires_authentication(self):
        self.unauthenticate()
        self.assertEqual(self.client.get(reverse('order-list')).status_code, 401)

    def test_create_sets_created_by_from_request(self):
        customer = factories.make_customer()

        response = self.client.post(
            reverse('order-list'), {'customer': str(customer.id)}
        )

        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(pk=response.data['id'])
        self.assertEqual(order.created_by, self.user)

    def test_order_number_is_read_only_on_create(self):
        customer = factories.make_customer()

        response = self.client.post(
            reverse('order-list'),
            {'customer': str(customer.id), 'order_number': 'ATTACKER-SET'},
        )

        self.assertEqual(response.status_code, 201)
        self.assertNotEqual(response.data['order_number'], 'ATTACKER-SET')

    def test_list_serializer_reports_item_count(self):
        order = factories.make_order()
        factories.make_order_item(order=order)

        response = self.client.get(reverse('order-list'))

        self.assertEqual(response.data['results'][0]['item_count'], 1)

    def test_detail_serializer_nests_customer_and_items(self):
        order = factories.make_order()
        factories.make_order_item(order=order)

        response = self.client.get(reverse('order-detail', args=[order.id]))

        self.assertEqual(response.data['customer']['id'], str(order.customer.id))
        self.assertEqual(len(response.data['items']), 1)

    def test_add_item_action_recalculates_totals(self):
        order = factories.make_order()
        product = factories.make_product(price=Decimal('100.00'))

        response = self.client.post(
            reverse('order-add-item', args=[order.id]),
            {'product': str(product.id), 'quantity': 2, 'unit_price': '100.00'},
        )

        self.assertEqual(response.status_code, 201)
        order.refresh_from_db()
        self.assertEqual(order.subtotal, Decimal('200.00'))
        self.assertEqual(order.total_amount, Decimal('220.00'))

    def test_add_item_rejects_invalid_payload(self):
        order = factories.make_order()

        response = self.client.post(
            reverse('order-add-item', args=[order.id]), {'quantity': 2}
        )

        self.assertEqual(response.status_code, 400)

    def test_update_status_records_history(self):
        order = factories.make_order()

        response = self.client.post(
            reverse('order-update-status', args=[order.id]),
            {'status': OrderStatus.CONFIRMED, 'notes': 'confirmed by ops'},
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CONFIRMED)

        history = OrderHistory.objects.get(order=order)
        self.assertEqual(history.status_from, OrderStatus.PENDING)
        self.assertEqual(history.status_to, OrderStatus.CONFIRMED)
        self.assertEqual(history.notes, 'confirmed by ops')
        self.assertEqual(history.changed_by, self.user)

    def test_update_status_requires_status(self):
        order = factories.make_order()

        response = self.client.post(
            reverse('order-update-status', args=[order.id]), {}
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(OrderHistory.objects.count(), 0)

    def test_items_action(self):
        order = factories.make_order()
        factories.make_order_item(order=order)
        factories.make_order_item(order=factories.make_order())

        response = self.client.get(reverse('order-items', args=[order.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_filter_by_status_and_type(self):
        factories.make_order(status=OrderStatus.PENDING)
        factories.make_order(status=OrderStatus.DELIVERED)

        response = self.client.get(
            reverse('order-list'), {'status': OrderStatus.DELIVERED}
        )

        self.assertEqual(response.data['count'], 1)

    def test_search_by_order_number(self):
        order = factories.make_order()
        factories.make_order()

        response = self.client.get(
            reverse('order-list'), {'search': order.order_number}
        )

        self.assertEqual(response.data['count'], 1)

    def test_order_item_viewset_filters_by_order(self):
        order = factories.make_order()
        factories.make_order_item(order=order)
        factories.make_order_item()

        response = self.client.get(
            reverse('orderitem-list'), {'order': str(order.id)}
        )

        self.assertEqual(response.data['count'], 1)


class OrderHistoryModelTests(AuthenticatedAPITestCase):
    def test_str(self):
        order = factories.make_order()
        history = OrderHistory.objects.create(
            order=order,
            status_from=OrderStatus.PENDING,
            status_to=OrderStatus.SHIPPED,
        )

        self.assertEqual(
            str(history),
            f'Order {order.order_number}: pending → shipped',
        )
