from rest_framework import serializers
from .models import Payment, Refund, StoredPaymentMethod
from customers.serializers import CustomerSerializer
from invoices.serializers import InvoiceSerializer


class StoredPaymentMethodSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)

    class Meta:
        model = StoredPaymentMethod
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at')
        extra_kwargs = {
            'stripe_payment_method_id': {'write_only': True},
            'paypal_payment_method_id': {'write_only': True},
        }


class PaymentSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True)
    processed_by_name = serializers.CharField(source='processed_by.username', read_only=True)

    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ('id', 'payment_reference', 'processed_at', 'created_at', 'updated_at')
        extra_kwargs = {
            'gateway_response': {'write_only': True},
        }

    def create(self, validated_data):
        if 'processed_by' not in validated_data:
            validated_data['processed_by'] = self.context['request'].user
        return super().create(validated_data)


class RefundSerializer(serializers.ModelSerializer):
    payment_reference = serializers.CharField(source='payment.payment_reference', read_only=True)
    processed_by_name = serializers.CharField(source='processed_by.username', read_only=True)

    class Meta:
        model = Refund
        fields = '__all__'
        read_only_fields = ('id', 'refund_reference', 'processed_at', 'created_at', 'updated_at')
        extra_kwargs = {
            'gateway_response': {'write_only': True},
        }

    def create(self, validated_data):
        if 'processed_by' not in validated_data:
            validated_data['processed_by'] = self.context['request'].user
        return super().create(validated_data)


class PaymentListSerializer(serializers.ModelSerializer):
    """Simplified serializer for payment listings"""
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True)

    class Meta:
        model = Payment
        fields = ('id', 'payment_reference', 'customer_name', 'invoice_number', 
                 'amount', 'payment_method', 'status', 'payment_date')


class PaymentDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer with all related data"""
    customer = CustomerSerializer(read_only=True)
    invoice = InvoiceSerializer(read_only=True)
    refunds = RefundSerializer(many=True, read_only=True)
    processed_by_name = serializers.CharField(source='processed_by.username', read_only=True)

    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ('id', 'payment_reference', 'processed_at', 'created_at', 'updated_at')
        extra_kwargs = {
            'gateway_response': {'write_only': True},
        }