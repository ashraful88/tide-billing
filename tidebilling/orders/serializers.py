from rest_framework import serializers
from .models import Order, OrderItem, OrderHistory
from customers.serializers import CustomerSerializer
from products.serializers import ProductSerializer


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(read_only=True)
    product_sku = serializers.CharField(read_only=True)

    class Meta:
        model = OrderItem
        fields = '__all__'
        read_only_fields = ('id', 'total_price', 'product_name', 'product_sku', 'created_at', 'updated_at')


class OrderHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(source='changed_by.username', read_only=True)

    class Meta:
        model = OrderHistory
        fields = '__all__'
        read_only_fields = ('id', 'changed_at')


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = Order
        fields = '__all__'
        read_only_fields = ('id', 'order_number', 'created_at', 'updated_at')

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class OrderListSerializer(serializers.ModelSerializer):
    """Simplified serializer for order listings"""
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ('id', 'order_number', 'customer_name', 'order_type', 'status', 
                 'total_amount', 'created_at', 'item_count')

    def get_item_count(self, obj):
        return obj.items.count()


class OrderDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer with all related data"""
    items = OrderItemSerializer(many=True, read_only=True)
    history = OrderHistorySerializer(many=True, read_only=True)
    customer = CustomerSerializer(read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = Order
        fields = '__all__'
        read_only_fields = ('id', 'order_number', 'created_at', 'updated_at')