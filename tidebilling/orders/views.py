from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q

from .models import Order, OrderItem, OrderHistory
from .serializers import (
    OrderSerializer, OrderItemSerializer, OrderHistorySerializer,
    OrderListSerializer, OrderDetailSerializer
)


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    permission_classes = [IsAuthenticated]
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
        serializer = OrderItemSerializer(data=request.data)
        
        if serializer.is_valid():
            serializer.save(order=order)
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


class OrderItemViewSet(viewsets.ModelViewSet):
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['order', 'product']
    search_fields = ['product_name', 'product_sku']
