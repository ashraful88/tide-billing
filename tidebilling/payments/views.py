from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from decimal import Decimal

from .models import Payment, Refund, StoredPaymentMethod
from .serializers import (
    PaymentSerializer, RefundSerializer, StoredPaymentMethodSerializer,
    PaymentListSerializer, PaymentDetailSerializer
)


class StoredPaymentMethodViewSet(viewsets.ModelViewSet):
    queryset = StoredPaymentMethod.objects.all()
    serializer_class = StoredPaymentMethodSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['customer', 'type', 'is_active', 'is_default']
    search_fields = ['customer__name', 'card_brand']
    ordering_fields = ['created_at', 'is_default']
    ordering = ['-is_default', '-created_at']


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'payment_method', 'payment_gateway', 'customer', 'invoice']
    search_fields = ['payment_reference', 'customer__name', 'invoice__invoice_number']
    ordering_fields = ['payment_date', 'amount', 'created_at']
    ordering = ['-payment_date']

    def get_serializer_class(self):
        if self.action == 'list':
            return PaymentListSerializer
        elif self.action == 'retrieve':
            return PaymentDetailSerializer
        return PaymentSerializer

    @action(detail=True, methods=['post'])
    def mark_completed(self, request, pk=None):
        """Mark payment as completed"""
        payment = self.get_object()
        
        if payment.status != 'pending':
            return Response({'detail': 'Only pending payments can be marked as completed.'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        payment.mark_as_completed()
        serializer = self.get_serializer(payment)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def mark_failed(self, request, pk=None):
        """Mark payment as failed"""
        payment = self.get_object()
        reason = request.data.get('reason', '')
        
        payment.mark_as_failed(reason)
        serializer = self.get_serializer(payment)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def create_refund(self, request, pk=None):
        """Create a refund for this payment"""
        payment = self.get_object()
        amount = request.data.get('amount')
        reason = request.data.get('reason', '')
        
        if not amount:
            return Response({'detail': 'Amount is required.'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        try:
            amount = Decimal(str(amount))
            if amount <= 0 or amount > payment.amount:
                return Response({'detail': 'Invalid refund amount.'}, 
                              status=status.HTTP_400_BAD_REQUEST)
        except (ValueError, TypeError):
            return Response({'detail': 'Invalid amount format.'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        refund = Refund.objects.create(
            payment=payment,
            amount=amount,
            reason=reason,
            processed_by=request.user
        )
        
        serializer = RefundSerializer(refund)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class RefundViewSet(viewsets.ModelViewSet):
    queryset = Refund.objects.all()
    serializer_class = RefundSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'payment__customer']
    search_fields = ['refund_reference', 'payment__payment_reference', 'reason']
    ordering_fields = ['refund_date', 'amount', 'created_at']
    ordering = ['-refund_date']
