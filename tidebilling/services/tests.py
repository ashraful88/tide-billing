from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone

from services.models import ServiceRequest, TimeLog
from tidebilling import factories
from tidebilling.apitest import AuthenticatedAPITestCase


class ServiceModelTests(AuthenticatedAPITestCase):
    def test_str_methods(self):
        category = factories.make_service_category(name='Consulting')
        service = factories.make_service(category=category, name='Advisory')

        self.assertEqual(str(category), 'Consulting')
        self.assertEqual(str(service), 'Advisory')

    def test_defaults(self):
        service = factories.make_service()

        self.assertTrue(service.is_active)
        self.assertFalse(service.is_featured)
        self.assertFalse(service.is_recurring)
        self.assertEqual(service.billing_frequency, 'one_time')

    def test_category_slug_is_unique(self):
        factories.make_service_category(slug='dup')
        with self.assertRaises(IntegrityError):
            factories.make_service_category(slug='dup')


class ServiceRequestModelTests(AuthenticatedAPITestCase):
    def test_request_number_generated(self):
        request = factories.make_service_request()

        self.assertRegex(request.request_number, r'^REQ-\d{8}-[0-9A-F]{8}$')

    def test_request_number_is_stable_across_saves(self):
        request = factories.make_service_request()
        original = request.request_number

        request.title = 'Renamed'
        request.save()

        self.assertEqual(request.request_number, original)

    def test_request_numbers_are_unique(self):
        numbers = {
            factories.make_service_request().request_number for _ in range(10)
        }

        self.assertEqual(len(numbers), 10)

    def test_defaults(self):
        request = factories.make_service_request()

        self.assertEqual(request.status, 'draft')
        self.assertEqual(request.priority, 'medium')
        self.assertEqual(request.actual_hours, Decimal('0.0'))
        self.assertEqual(request.attachments, [])

    def test_str(self):
        request = factories.make_service_request(title='Build a thing')

        self.assertEqual(
            str(request), f'Request {request.request_number} - Build a thing'
        )


class TimeLogModelTests(AuthenticatedAPITestCase):
    def test_hours_derived_from_start_and_end(self):
        start = timezone.now()
        log = factories.make_time_log(
            start_time=start, end_time=start + timedelta(hours=2, minutes=30)
        )

        self.assertEqual(log.hours, Decimal('2.50'))

    def test_hours_not_computed_without_end_time(self):
        log = factories.make_time_log()

        self.assertIsNone(log.hours)

    def test_explicit_hours_are_not_overwritten(self):
        start = timezone.now()
        log = factories.make_time_log(
            start_time=start,
            end_time=start + timedelta(hours=8),
            hours=Decimal('1.00'),
        )

        self.assertEqual(log.hours, Decimal('1.00'))

    def test_str(self):
        user = factories.make_user(username='worker')
        start = timezone.now()
        log = factories.make_time_log(
            user=user, start_time=start, end_time=start + timedelta(hours=1)
        )

        self.assertEqual(
            str(log),
            f'{log.service_request.request_number} - worker - {log.hours}h',
        )


class ServiceFeedbackModelTests(AuthenticatedAPITestCase):
    def test_str(self):
        request = factories.make_service_request()
        feedback = factories.make_feedback(
            service_request=request, overall_rating=4
        )

        self.assertEqual(
            str(feedback), f'Feedback for {request.request_number} - 4/5'
        )

    def test_one_feedback_per_request(self):
        request = factories.make_service_request()
        factories.make_feedback(service_request=request)

        with self.assertRaises(IntegrityError):
            factories.make_feedback(service_request=request)


class ServiceAPITests(AuthenticatedAPITestCase):
    def test_requires_authentication(self):
        self.unauthenticate()
        self.assertEqual(self.client.get(reverse('service-list')).status_code, 401)

    def test_category_reports_active_service_count(self):
        category = factories.make_service_category()
        factories.make_service(category=category, is_active=True)
        factories.make_service(category=category, is_active=False)

        response = self.client.get(reverse('servicecategory-list'))

        self.assertEqual(response.data['results'][0]['service_count'], 1)

    def test_active_action(self):
        factories.make_service(is_active=True)
        factories.make_service(is_active=False)

        response = self.client.get(reverse('service-active'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_filter_by_category(self):
        category = factories.make_service_category()
        factories.make_service(category=category)
        factories.make_service()

        response = self.client.get(
            reverse('service-list'), {'category': category.pk}
        )

        self.assertEqual(response.data['count'], 1)


class ServiceRequestAPITests(AuthenticatedAPITestCase):
    def test_create_sets_created_by(self):
        customer = factories.make_customer()
        service = factories.make_service()

        response = self.client.post(
            reverse('servicerequest-list'),
            {
                'customer': str(customer.id),
                'service': str(service.id),
                'title': 'New request',
                'description': 'Please do the thing',
            },
        )

        self.assertEqual(response.status_code, 201)
        request = ServiceRequest.objects.get(pk=response.data['id'])
        self.assertEqual(request.created_by, self.user)

    def test_assign_action(self):
        request = factories.make_service_request()
        assignee = factories.make_user(username='assignee')

        response = self.client.post(
            reverse('servicerequest-assign', args=[request.id]),
            {'user_id': assignee.id},
        )

        self.assertEqual(response.status_code, 200)
        request.refresh_from_db()
        self.assertEqual(request.assigned_to, assignee)

    def test_assign_requires_user_id(self):
        request = factories.make_service_request()

        response = self.client.post(
            reverse('servicerequest-assign', args=[request.id]), {}
        )

        self.assertEqual(response.status_code, 400)

    def test_assign_with_unknown_user_returns_404(self):
        request = factories.make_service_request()

        response = self.client.post(
            reverse('servicerequest-assign', args=[request.id]),
            {'user_id': 999999},
        )

        self.assertEqual(response.status_code, 404)

    def test_update_status_stamps_started_at(self):
        request = factories.make_service_request()

        response = self.client.post(
            reverse('servicerequest-update-status', args=[request.id]),
            {'status': 'in_progress'},
        )

        self.assertEqual(response.status_code, 200)
        request.refresh_from_db()
        self.assertEqual(request.status, 'in_progress')
        self.assertIsNotNone(request.started_at)
        self.assertIsNone(request.completed_at)

    def test_update_status_stamps_completed_at(self):
        request = factories.make_service_request()

        self.client.post(
            reverse('servicerequest-update-status', args=[request.id]),
            {'status': 'completed'},
        )

        request.refresh_from_db()
        self.assertIsNotNone(request.completed_at)

    def test_update_status_does_not_overwrite_existing_started_at(self):
        original = timezone.now() - timedelta(days=2)
        request = factories.make_service_request(started_at=original)

        self.client.post(
            reverse('servicerequest-update-status', args=[request.id]),
            {'status': 'in_progress'},
        )

        request.refresh_from_db()
        self.assertEqual(request.started_at, original)

    def test_update_status_requires_status(self):
        request = factories.make_service_request()

        response = self.client.post(
            reverse('servicerequest-update-status', args=[request.id]), {}
        )

        self.assertEqual(response.status_code, 400)

    def test_deliverables_action(self):
        request = factories.make_service_request()
        factories.make_deliverable(service_request=request)
        factories.make_deliverable()

        response = self.client.get(
            reverse('servicerequest-deliverables', args=[request.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_time_logs_action(self):
        request = factories.make_service_request()
        factories.make_time_log(service_request=request)
        factories.make_time_log()

        response = self.client.get(
            reverse('servicerequest-time-logs', args=[request.id])
        )

        self.assertEqual(len(response.data), 1)

    def test_detail_serializer_nests_related_objects(self):
        request = factories.make_service_request()
        factories.make_deliverable(service_request=request)
        factories.make_time_log(service_request=request)
        factories.make_feedback(service_request=request)

        response = self.client.get(
            reverse('servicerequest-detail', args=[request.id])
        )

        self.assertEqual(len(response.data['deliverables']), 1)
        self.assertEqual(len(response.data['time_logs']), 1)
        self.assertIsNotNone(response.data['feedback'])

    def test_filter_by_status_and_priority(self):
        factories.make_service_request(status='draft', priority='low')
        factories.make_service_request(status='completed', priority='urgent')

        response = self.client.get(
            reverse('servicerequest-list'), {'priority': 'urgent'}
        )

        self.assertEqual(response.data['count'], 1)


class ServiceDeliverableAPITests(AuthenticatedAPITestCase):
    def test_mark_completed_action(self):
        deliverable = factories.make_deliverable()

        response = self.client.post(
            reverse('servicedeliverable-mark-completed', args=[deliverable.id])
        )

        self.assertEqual(response.status_code, 200)
        deliverable.refresh_from_db()
        self.assertTrue(deliverable.is_completed)
        self.assertIsNotNone(deliverable.completed_at)

    def test_filter_by_completion(self):
        factories.make_deliverable(is_completed=True)
        factories.make_deliverable(is_completed=False)

        response = self.client.get(
            reverse('servicedeliverable-list'), {'is_completed': 'true'}
        )

        self.assertEqual(response.data['count'], 1)


class TimeLogAPITests(AuthenticatedAPITestCase):
    def test_create_assigns_the_requesting_user(self):
        request = factories.make_service_request()
        start = timezone.now()

        response = self.client.post(
            reverse('timelog-list'),
            {
                'service_request': str(request.id),
                'start_time': start.isoformat(),
                'end_time': (start + timedelta(hours=3)).isoformat(),
                'description': 'Did the work',
            },
        )

        self.assertEqual(response.status_code, 201)
        log = TimeLog.objects.get(pk=response.data['id'])
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.hours, Decimal('3.00'))

    def test_filter_by_billable(self):
        factories.make_time_log(is_billable=True)
        factories.make_time_log(is_billable=False)

        response = self.client.get(
            reverse('timelog-list'), {'is_billable': 'false'}
        )

        self.assertEqual(response.data['count'], 1)


class ServiceFeedbackAPITests(AuthenticatedAPITestCase):
    def test_create_and_filter(self):
        request = factories.make_service_request()

        create = self.client.post(
            reverse('servicefeedback-list'),
            {
                'service_request': str(request.id),
                'overall_rating': 5,
                'would_recommend': True,
            },
        )
        self.assertEqual(create.status_code, 201)

        response = self.client.get(
            reverse('servicefeedback-list'), {'overall_rating': 5}
        )
        self.assertEqual(response.data['count'], 1)

    def test_rating_must_be_a_valid_choice(self):
        request = factories.make_service_request()

        response = self.client.post(
            reverse('servicefeedback-list'),
            {'service_request': str(request.id), 'overall_rating': 9},
        )

        self.assertEqual(response.status_code, 400)
