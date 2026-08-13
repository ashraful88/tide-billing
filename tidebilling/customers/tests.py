from django.db import IntegrityError
from django.urls import reverse

from customers.models import Customer
from tidebilling import factories
from tidebilling.apitest import AuthenticatedAPITestCase


class CustomerModelTests(AuthenticatedAPITestCase):
    def test_str_is_name(self):
        customer = factories.make_customer(name='Acme Corp')
        self.assertEqual(str(customer), 'Acme Corp')

    def test_email_is_unique(self):
        factories.make_customer(email='dup@example.com')
        with self.assertRaises(IntegrityError):
            factories.make_customer(email='dup@example.com')

    def test_cus_id_is_unique(self):
        factories.make_customer(cus_id=4242)
        with self.assertRaises(IntegrityError):
            factories.make_customer(cus_id=4242)

    def test_defaults(self):
        customer = factories.make_customer()
        self.assertTrue(customer.status)
        self.assertIsNotNone(customer.created)
        self.assertIsNotNone(customer.modified)

    def test_contact_str_is_name(self):
        contact = factories.make_contact(name='Jane Doe')
        self.assertEqual(str(contact), 'Jane Doe')


class CustomerAPITests(AuthenticatedAPITestCase):
    def test_requires_authentication(self):
        self.unauthenticate()
        response = self.client.get(reverse('customer-list'))
        self.assertEqual(response.status_code, 401)

    def test_list_uses_list_serializer(self):
        customer = factories.make_customer()
        factories.make_contact(customer=customer)

        response = self.client.get(reverse('customer-list'))

        self.assertEqual(response.status_code, 200)
        row = response.data['results'][0]
        self.assertEqual(row['contact_count'], 1)
        # The flat list serializer must not carry the detail-only `note` field.
        self.assertNotIn('note', row)

    def test_retrieve_uses_detail_serializer(self):
        customer = factories.make_customer()
        factories.make_contact(customer=customer)

        response = self.client.get(
            reverse('customer-detail', args=[customer.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['contacts']), 1)

    def test_create(self):
        response = self.client.post(
            reverse('customer-list'),
            {
                'cus_id': 9001,
                'name': 'New Customer',
                'email': 'new@example.com',
                'phone': '+15550000',
                'note': 'hello',
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(Customer.objects.filter(email='new@example.com').exists())

    def test_create_rejects_duplicate_email(self):
        factories.make_customer(email='taken@example.com')

        response = self.client.post(
            reverse('customer-list'),
            {
                'cus_id': 9002,
                'name': 'Dup',
                'email': 'taken@example.com',
                'phone': '+15550001',
                'note': '',
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.data)

    def test_update_keeps_own_email(self):
        """The uniqueness validator must exclude the instance being updated."""
        customer = factories.make_customer(email='self@example.com')

        response = self.client.patch(
            reverse('customer-detail', args=[customer.id]),
            {'email': 'self@example.com', 'name': 'Renamed'},
        )

        self.assertEqual(response.status_code, 200)
        customer.refresh_from_db()
        self.assertEqual(customer.name, 'Renamed')

    def test_delete(self):
        customer = factories.make_customer()

        response = self.client.delete(
            reverse('customer-detail', args=[customer.id])
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Customer.objects.filter(pk=customer.pk).exists())

    def test_contacts_action(self):
        customer = factories.make_customer()
        factories.make_contact(customer=customer, name='Contact A')
        factories.make_contact(customer=factories.make_customer())

        response = self.client.get(
            reverse('customer-contacts', args=[customer.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([c['name'] for c in response.data], ['Contact A'])

    def test_search_action(self):
        factories.make_customer(name='Findable Industries')
        factories.make_customer(name='Other')

        response = self.client.get(
            reverse('customer-search'), {'q': 'Findable'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_search_matches_note_field(self):
        factories.make_customer(note='vip account')

        response = self.client.get(reverse('customer-search'), {'q': 'vip'})

        self.assertEqual(len(response.data), 1)

    def test_search_requires_query(self):
        response = self.client.get(reverse('customer-search'))

        self.assertEqual(response.status_code, 400)

    def test_filter_by_status(self):
        factories.make_customer(status=True)
        factories.make_customer(status=False)

        response = self.client.get(reverse('customer-list'), {'status': 'false'})

        self.assertEqual(response.data['count'], 1)

    def test_search_backend(self):
        factories.make_customer(name='Searchable Ltd')
        factories.make_customer(name='Unrelated')

        response = self.client.get(reverse('customer-list'), {'search': 'Searchable'})

        self.assertEqual(response.data['count'], 1)

    def test_ordering_backend(self):
        factories.make_customer(name='Zeta')
        factories.make_customer(name='Alpha')

        response = self.client.get(reverse('customer-list'), {'ordering': 'name'})

        names = [row['name'] for row in response.data['results']]
        self.assertEqual(names, sorted(names))


class CustomerContactAPITests(AuthenticatedAPITestCase):
    def test_create_and_filter_by_customer(self):
        customer = factories.make_customer()

        create = self.client.post(
            reverse('customercontact-list'),
            {
                'name': 'Contact',
                'email': 'c@example.com',
                'phone': '+15551234',
                'customer': str(customer.id),
            },
        )
        self.assertEqual(create.status_code, 201)

        response = self.client.get(
            reverse('customercontact-list'), {'customer': str(customer.id)}
        )
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(
            response.data['results'][0]['customer_name'], customer.name
        )
