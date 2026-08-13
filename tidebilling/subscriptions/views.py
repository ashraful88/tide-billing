from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone

from .models import SubscriptionPlan, Subscription, SubscriptionChange, SubscriptionUsage
from .serializers import (
    SubscriptionPlanSerializer, SubscriptionSerializer, SubscriptionChangeSerializer,
    SubscriptionUsageSerializer, SubscriptionListSerializer, SubscriptionDetailSerializer
)


class SubscriptionPlanViewSet(viewsets.ModelViewSet):
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'is_featured', 'billing_frequency']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'price', 'created_at']
    ordering = ['price']

    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get active subscription plans"""
        plans = self.queryset.filter(is_active=True)
        serializer = self.get_serializer(plans, many=True)
        return Response(serializer.data)


class SubscriptionViewSet(viewsets.ModelViewSet):
    queryset = Subscription.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'plan', 'customer']
    search_fields = ['subscription_number', 'customer__name', 'plan__name']
    ordering_fields = ['created_at', 'start_date', 'next_billing_date']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return SubscriptionListSerializer
        elif self.action == 'retrieve':
            return SubscriptionDetailSerializer
        return SubscriptionSerializer

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel subscription"""
        subscription = self.get_object()
        reason = request.data.get('reason', '')
        at_period_end = request.data.get('at_period_end', True)
        
        subscription.cancel(reason=reason, at_period_end=at_period_end)
        serializer = self.get_serializer(subscription)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def reactivate(self, request, pk=None):
        """Reactivate subscription"""
        subscription = self.get_object()
        
        if subscription.status != 'cancelled':
            return Response({'detail': 'Only cancelled subscriptions can be reactivated.'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        subscription.reactivate()
        serializer = self.get_serializer(subscription)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def upgrade(self, request, pk=None):
        """Upgrade subscription plan"""
        subscription = self.get_object()
        new_plan_id = request.data.get('plan_id')
        
        if not new_plan_id:
            return Response({'detail': 'Plan ID is required.'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        try:
            from .models import SubscriptionPlan
            new_plan = SubscriptionPlan.objects.get(id=new_plan_id)
            subscription.upgrade_plan(new_plan)
            serializer = self.get_serializer(subscription)
            return Response(serializer.data)
        except SubscriptionPlan.DoesNotExist:
            return Response({'detail': 'Plan not found.'}, 
                          status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'])
    def add_usage(self, request, pk=None):
        """Add usage to subscription"""
        subscription = self.get_object()
        metric = request.data.get('metric')
        amount = request.data.get('amount')
        
        if not metric or amount is None:
            return Response({'detail': 'Metric and amount are required.'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        try:
            amount = float(amount)
            subscription.add_usage(metric, amount)
            serializer = self.get_serializer(subscription)
            return Response(serializer.data)
        except ValueError:
            return Response({'detail': 'Invalid amount value.'}, 
                          status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def expiring_soon(self, request):
        """Get subscriptions expiring within specified days"""
        days = int(request.query_params.get('days', 7))
        expiry_date = timezone.now() + timezone.timedelta(days=days)
        
        subscriptions = Subscription.objects.filter(
            current_period_end__lte=expiry_date,
            status='active'
        )
        serializer = SubscriptionListSerializer(subscriptions, many=True)
        return Response(serializer.data)


class SubscriptionChangeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SubscriptionChange.objects.all()
    serializer_class = SubscriptionChangeSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['subscription', 'change_type']
    search_fields = ['subscription__subscription_number', 'reason']
    ordering_fields = ['created_at', 'effective_date']
    ordering = ['-created_at']


class SubscriptionUsageViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SubscriptionUsage.objects.all()
    serializer_class = SubscriptionUsageSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['subscription', 'metric_name']
    search_fields = ['subscription__subscription_number', 'metric_name']
    ordering_fields = ['recorded_at', 'billing_period_start']
    ordering = ['-recorded_at']
