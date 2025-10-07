from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone

from .models import (
    ServiceCategory, Service, ServiceRequest, ServiceDeliverable, 
    TimeLog, ServiceFeedback
)
from .serializers import (
    ServiceCategorySerializer, ServiceSerializer, ServiceRequestSerializer,
    ServiceDeliverableSerializer, TimeLogSerializer, ServiceFeedbackSerializer,
    ServiceRequestListSerializer, ServiceRequestDetailSerializer
)


class ServiceCategoryViewSet(viewsets.ModelViewSet):
    queryset = ServiceCategory.objects.all()
    serializer_class = ServiceCategorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']


class ServiceViewSet(viewsets.ModelViewSet):
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'is_featured', 'category', 'billing_frequency']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'base_price', 'created_at']
    ordering = ['name']

    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get active services"""
        services = self.queryset.filter(is_active=True)
        serializer = self.get_serializer(services, many=True)
        return Response(serializer.data)


class ServiceRequestViewSet(viewsets.ModelViewSet):
    queryset = ServiceRequest.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'priority', 'customer', 'service', 'assigned_to']
    search_fields = ['request_number', 'title', 'description', 'customer__name']
    ordering_fields = ['created_at', 'priority', 'requested_completion_date']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return ServiceRequestListSerializer
        elif self.action == 'retrieve':
            return ServiceRequestDetailSerializer
        return ServiceRequestSerializer

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """Assign service request to a user"""
        service_request = self.get_object()
        user_id = request.data.get('user_id')
        
        if not user_id:
            return Response({'detail': 'User ID is required.'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        try:
            from django.contrib.auth.models import User
            user = User.objects.get(id=user_id)
            service_request.assigned_to = user
            service_request.save()
            
            serializer = self.get_serializer(service_request)
            return Response(serializer.data)
        except User.DoesNotExist:
            return Response({'detail': 'User not found.'}, 
                          status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update service request status"""
        service_request = self.get_object()
        new_status = request.data.get('status')
        
        if not new_status:
            return Response({'detail': 'Status is required.'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        service_request.status = new_status
        
        # Update timestamps based on status
        now = timezone.now()
        if new_status == 'in_progress' and not service_request.started_at:
            service_request.started_at = now
        elif new_status == 'completed' and not service_request.completed_at:
            service_request.completed_at = now
        
        service_request.save()
        serializer = self.get_serializer(service_request)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def deliverables(self, request, pk=None):
        """Get service request deliverables"""
        service_request = self.get_object()
        deliverables = service_request.deliverables.all()
        serializer = ServiceDeliverableSerializer(deliverables, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def time_logs(self, request, pk=None):
        """Get service request time logs"""
        service_request = self.get_object()
        time_logs = service_request.time_logs.all()
        serializer = TimeLogSerializer(time_logs, many=True)
        return Response(serializer.data)


class ServiceDeliverableViewSet(viewsets.ModelViewSet):
    queryset = ServiceDeliverable.objects.all()
    serializer_class = ServiceDeliverableSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['service_request', 'is_completed']
    search_fields = ['title', 'description']
    ordering_fields = ['due_date', 'created_at']
    ordering = ['due_date']

    @action(detail=True, methods=['post'])
    def mark_completed(self, request, pk=None):
        """Mark deliverable as completed"""
        deliverable = self.get_object()
        deliverable.is_completed = True
        deliverable.completed_at = timezone.now()
        deliverable.save()
        
        serializer = self.get_serializer(deliverable)
        return Response(serializer.data)


class TimeLogViewSet(viewsets.ModelViewSet):
    queryset = TimeLog.objects.all()
    serializer_class = TimeLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['service_request', 'user', 'is_billable']
    search_fields = ['description', 'service_request__title']
    ordering_fields = ['start_time', 'hours', 'created_at']
    ordering = ['-start_time']

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ServiceFeedbackViewSet(viewsets.ModelViewSet):
    queryset = ServiceFeedback.objects.all()
    serializer_class = ServiceFeedbackSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['service_request', 'overall_rating', 'would_recommend']
    search_fields = ['positive_feedback', 'improvement_suggestions']
    ordering_fields = ['created_at', 'overall_rating']
    ordering = ['-created_at']
