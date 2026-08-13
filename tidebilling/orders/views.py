from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from tidebilling.permissions import IsBillingStaffOrReadOnly
from django.db.models import Q

from .models import Order, OrderItem, OrderHistory
from .serializers import (
    OrderSerializer, OrderItemSerializer, OrderHistorySerializer,
    OrderListSerializer, OrderDetailSerializer
)


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    permission_classes = [IsBillingStaffOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'order_type', 'customer']
    search_fields = ['order_number', 'customer__name', 'notes']
    ordering_fields = ['created_at', 'updated_at', 'total_amount']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return OrderListSerializer
        elif self.action == 'retrieve':
            return OrderDetailSerializer
        return OrderSerializer

    @action(detail=True, methods=['post'])
    def add_item(self, request, pk=None):
        """Add item to order"""
        order = self.get_object()
        # `order` is a required field on OrderItemSerializer (fields = '__all__'),
        # so inject it from the URL rather than making callers repeat it in the body.
        data = request.data.copy()
        data['order'] = order.pk
        serializer = OrderItemSerializer(data=data)

        if serializer.is_valid():
            serializer.save()
            order.calculate_totals()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update order status"""
        order = self.get_object()
        new_status = request.data.get('status')
        notes = request.data.get('notes', '')
        
        if not new_status:
            return Response({'detail': 'Status is required.'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        old_status = order.status
        order.status = new_status
        order.save()
        
        # Create history record
        OrderHistory.objects.create(
            order=order,
            status_from=old_status,
            status_to=new_status,
            notes=notes,
            changed_by=request.user
        )
        
        serializer = self.get_serializer(order)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def items(self, request, pk=None):
        """Get order items"""
        order = self.get_object()
        items = order.items.all()
        serializer = OrderItemSerializer(items, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='generate_invoice')
    def generate_invoice(self, request, pk=None):
        """Raise an invoice for this order.

        Wires up the Order -> Invoice -> Payment flow, which previously had no
        caller: `generate_invoice_from_order` existed but nothing invoked it.
        Idempotent -- an order already invoiced returns its existing invoice.
        """
        from invoices.models import Invoice
        from invoices.serializers import InvoiceSerializer
        from invoices.tasks import generate_invoice_from_order

        order = self.get_object()
        existing = order.invoices.first()
        already_invoiced = existing is not None

        invoice_id = generate_invoice_from_order(order.id, user_id=request.user.pk)
        if invoice_id is None:
            return Response(
                {'detail': 'Could not generate an invoice for this order.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invoice = Invoice.objects.get(pk=invoice_id)
        return Response(
            InvoiceSerializer(invoice, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK if already_invoiced else status.HTTP_201_CREATED,
        )


class OrderItemViewSet(viewsets.ModelViewSet):
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer
    permission_classes = [IsBillingStaffOrReadOnly]
    # OrderItem has no Meta.ordering; without a deterministic order the
    # paginator can repeat or skip rows across pages.
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['order', 'product']
    search_fields = ['product_name', 'product_sku']
    ordering_fields = ['created_at', 'total_price', 'quantity']
    ordering = ['-created_at']
