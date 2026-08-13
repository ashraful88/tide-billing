from rest_framework import serializers
from .models import Invoice, InvoiceItem, InvoiceHistory
from customers.serializers import CustomerSerializer
from orders.serializers import OrderSerializer


class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = '__all__'
        read_only_fields = ('id', 'total_price', 'created_at', 'updated_at')


class InvoiceHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(source='changed_by.username', read_only=True)

    class Meta:
        model = InvoiceHistory
        fields = '__all__'
        read_only_fields = ('id', 'changed_at')


class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    is_finalized = serializers.BooleanField(read_only=True)

    class Meta:
        model = Invoice
        fields = '__all__'
        read_only_fields = ('id', 'invoice_number', 'outstanding_amount', 'reminder_count',
                           'last_reminder_at', 'created_at', 'updated_at')

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class InvoiceListSerializer(serializers.ModelSerializer):
    """Simplified serializer for invoice listings"""
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = ('id', 'invoice_number', 'customer_name', 'status', 'total_amount', 
                 'outstanding_amount', 'due_date', 'is_overdue', 'created_at', 'item_count')

    def get_item_count(self, obj):
        return obj.items.count()


class InvoiceDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer with all related data"""
    items = InvoiceItemSerializer(many=True, read_only=True)
    history = InvoiceHistorySerializer(many=True, read_only=True)
    customer = CustomerSerializer(read_only=True)
    order = OrderSerializer(read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    is_finalized = serializers.BooleanField(read_only=True)

    class Meta:
        model = Invoice
        fields = '__all__'
        read_only_fields = ('id', 'invoice_number', 'outstanding_amount', 'reminder_count',
                           'last_reminder_at', 'created_at', 'updated_at')