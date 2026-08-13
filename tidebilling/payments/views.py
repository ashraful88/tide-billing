from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.core.exceptions import ValidationError
from decimal import Decimal, InvalidOperation

from tidebilling.permissions import IsBillingStaffOrReadOnly

from .models import Payment, PaymentStateError, PaymentStatus, Refund, StoredPaymentMethod
from .serializers import (
    PaymentSerializer, RefundSerializer, StoredPaymentMethodSerializer,
    PaymentListSerializer, PaymentDetailSerializer
)


def _validation_error_response(exc):
    detail = exc.messages[0] if getattr(exc, 'messages', None) else str(exc)
    return Response({'detail': detail}, status=status.HTTP_400_BAD_REQUEST)


class StoredPaymentMethodViewSet(viewsets.ModelViewSet):
    queryset = StoredPaymentMethod.objects.all()
    serializer_class = StoredPaymentMethodSerializer
    permission_classes = [IsBillingStaffOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['customer', 'type', 'is_active', 'is_default']
    search_fields = ['customer__name', 'card_brand']
    ordering_fields = ['created_at', 'is_default']
    ordering = ['-is_default', '-created_at']


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all()
    permission_classes = [IsBillingStaffOrReadOnly]
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

        try:
            payment.mark_as_completed(user=request.user)
        except PaymentStateError as exc:
            return _validation_error_response(exc)

        serializer = self.get_serializer(payment)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def mark_failed(self, request, pk=None):
        """Mark payment as failed"""
        payment = self.get_object()
        reason = request.data.get('reason', '')

        try:
            payment.mark_as_failed(reason, user=request.user)
        except PaymentStateError as exc:
            return _validation_error_response(exc)

        serializer = self.get_serializer(payment)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def create_refund(self, request, pk=None):
        """Create a refund for this payment.

        Created pending; call refunds/{id}/complete to settle it against the
        invoice.
        """
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
        except (InvalidOperation, ValueError, TypeError):
            # Decimal('abc') raises decimal.InvalidOperation, which is an
            # ArithmeticError rather than a ValueError, so it must be listed
            # explicitly or a non-numeric amount escapes as a 500.
            return Response({'detail': 'Invalid amount format.'},
                          status=status.HTTP_400_BAD_REQUEST)

        refund = Refund(
            payment=payment,
            amount=amount,
            reason=reason,
            processed_by=request.user,
        )
        try:
            # Enforces the cumulative cap across all refunds on this payment.
            refund.full_clean(exclude=['refund_reference'])
        except ValidationError as exc:
            return _validation_error_response(exc)
        refund.save()

        serializer = RefundSerializer(refund)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class RefundViewSet(viewsets.ModelViewSet):
    queryset = Refund.objects.all()
    serializer_class = RefundSerializer
    permission_classes = [IsBillingStaffOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'payment__customer']
    search_fields = ['refund_reference', 'payment__payment_reference', 'reason']
    ordering_fields = ['refund_date', 'amount', 'created_at']
    ordering = ['-refund_date']

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Settle the refund against its payment and invoice."""
        refund = self.get_object()
        try:
            refund.mark_as_completed(user=request.user)
        except PaymentStateError as exc:
            return _validation_error_response(exc)
        return Response(self.get_serializer(refund).data)
