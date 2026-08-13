from decimal import Decimal

from django.db import IntegrityError
from django.urls import reverse

from products.models import Product, image_file_path
from tidebilling import factories
from tidebilling.apitest import AuthenticatedAPITestCase


class ProductModelTests(AuthenticatedAPITestCase):
    def test_str_methods(self):
        category = factories.make_category(title='Widgets')
        subcategory = factories.make_subcategory(parent=category, title='Small')
        tag = factories.make_tag(slug='sale')
        product = factories.make_product(title='Widget')

        self.assertEqual(str(category), 'Widgets')
        self.assertEqual(str(subcategory), 'Small')
        self.assertEqual(str(tag), 'sale')
        self.assertEqual(str(product), 'Widget')

    def test_sku_is_unique(self):
        factories.make_product(sku='DUP-1')
        with self.assertRaises(IntegrityError):
            factories.make_product(sku='DUP-1')

    def test_image_file_path_randomises_name_and_keeps_extension(self):
        path = image_file_path(None, 'photo.png')

        self.assertTrue(path.startswith('uploads/products/'))
        self.assertTrue(path.endswith('.png'))
        self.assertNotIn('photo', path)

    def test_m2m_relations(self):
        product = factories.make_product()
        category = factories.make_category()
        tag = factories.make_tag()
        product.category.add(category)
        product.tags.add(tag)

        self.assertEqual(product.category.count(), 1)
        self.assertEqual(product.tags.count(), 1)


class ProductAPITests(AuthenticatedAPITestCase):
    def test_requires_authentication(self):
        self.unauthenticate()
        self.assertEqual(self.client.get(reverse('product-list')).status_code, 401)

    def _payload(self, **overrides):
        payload = {
            'title': 'New Product',
            'sku': 'NEW-1',
            'slug': 'new-product',
            'qty': 5,
            'base_price': '10.00',
            'price': '20.00',
            'body': 'Body text',
            'category': [factories.make_category().pk],
            'tags': [factories.make_tag().pk],
        }
        payload.update(overrides)
        return payload

    def test_create(self):
        response = self.client.post(reverse('product-list'), self._payload())

        self.assertEqual(response.status_code, 201)
        self.assertTrue(Product.objects.filter(sku='NEW-1').exists())

    def test_create_requires_category_and_tags(self):
        """Neither M2M declares blank=True, so both are mandatory on write.

        Recorded as current behaviour: requiring at least one *tag* to create a
        product is likely unintentional, but relaxing it needs a migration.
        """
        response = self.client.post(
            reverse('product-list'),
            self._payload(category=[], tags=[]),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('category', response.data)
        self.assertIn('tags', response.data)

    def test_create_rejects_duplicate_sku(self):
        factories.make_product(sku='TAKEN')

        response = self.client.post(
            reverse('product-list'), self._payload(sku='TAKEN', slug='dup')
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('sku', response.data)

    def test_list_serializer_reports_category_count(self):
        product = factories.make_product()
        product.category.add(factories.make_category())

        response = self.client.get(reverse('product-list'))

        self.assertEqual(response.data['results'][0]['category_count'], 1)

    def test_detail_serializer_nests_categories_and_tags(self):
        product = factories.make_product()
        product.category.add(factories.make_category(title='Nested'))
        product.tags.add(factories.make_tag(slug='nested-tag'))

        response = self.client.get(reverse('product-detail', args=[product.id]))

        self.assertEqual(response.data['categories'][0]['title'], 'Nested')
        self.assertEqual(response.data['tags'][0]['slug'], 'nested-tag')

    def test_low_stock_uses_default_threshold(self):
        factories.make_product(qty=5)
        factories.make_product(qty=50)

        response = self.client.get(reverse('product-low-stock'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_low_stock_honours_threshold_param(self):
        factories.make_product(qty=5)
        factories.make_product(qty=50)

        response = self.client.get(
            reverse('product-low-stock'), {'threshold': 100}
        )

        self.assertEqual(len(response.data), 2)

    def test_low_stock_excludes_unpublished(self):
        factories.make_product(qty=1, publish=False)

        response = self.client.get(reverse('product-low-stock'))

        self.assertEqual(len(response.data), 0)

    def test_update_stock(self):
        product = factories.make_product(qty=1)

        response = self.client.post(
            reverse('product-update-stock', args=[product.id]),
            {'quantity': 42},
        )

        self.assertEqual(response.status_code, 200)
        product.refresh_from_db()
        self.assertEqual(product.qty, 42)

    def test_update_stock_requires_quantity(self):
        product = factories.make_product()

        response = self.client.post(
            reverse('product-update-stock', args=[product.id]), {}
        )

        self.assertEqual(response.status_code, 400)

    def test_update_stock_rejects_non_numeric(self):
        product = factories.make_product()

        response = self.client.post(
            reverse('product-update-stock', args=[product.id]),
            {'quantity': 'abc'},
        )

        self.assertEqual(response.status_code, 400)

    def test_filter_by_publish(self):
        factories.make_product(publish=True)
        factories.make_product(publish=False)

        response = self.client.get(reverse('product-list'), {'publish': 'true'})

        self.assertEqual(response.data['count'], 1)

    def test_ordering_by_price(self):
        factories.make_product(price=Decimal('300.00'))
        factories.make_product(price=Decimal('100.00'))

        response = self.client.get(reverse('product-list'), {'ordering': 'price'})

        prices = [row['price'] for row in response.data['results']]
        self.assertEqual(prices, sorted(prices))


class CategoryAPITests(AuthenticatedAPITestCase):
    def test_category_crud(self):
        create = self.client.post(
            reverse('category-list'),
            {'title': 'Cat', 'cat_id': 1234, 'slug': 'cat', 'des': ''},
        )
        self.assertEqual(create.status_code, 201)

        listing = self.client.get(reverse('category-list'))
        self.assertEqual(listing.data['count'], 1)

    def test_subcategory_exposes_parent_name(self):
        parent = factories.make_category(title='Parent Cat')
        factories.make_subcategory(parent=parent)

        response = self.client.get(reverse('subcategory-list'))

        self.assertEqual(
            response.data['results'][0]['parent_name'], 'Parent Cat'
        )

    def test_subcategory_filter_by_parent(self):
        parent = factories.make_category()
        factories.make_subcategory(parent=parent)
        factories.make_subcategory()

        response = self.client.get(
            reverse('subcategory-list'), {'parent': parent.pk}
        )

        self.assertEqual(response.data['count'], 1)

    def test_tag_list(self):
        factories.make_tag(slug='alpha')

        response = self.client.get(reverse('tag-list'))

        self.assertEqual(response.data['count'], 1)
