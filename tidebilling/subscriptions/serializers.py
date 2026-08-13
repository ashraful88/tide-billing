from rest_framework import serializers
from .models import SubscriptionPlan, Subscription, SubscriptionChange, SubscriptionUsage
from customers.serializers import CustomerSerializer
from payments.serializers import StoredPaymentMethodSerializer


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    monthly_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = SubscriptionPlan
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at')


class SubscriptionChangeSerializer(serializers.ModelSerializer):
    old_plan_name = serializers.CharField(source='old_plan.name', read_only=True)
    new_plan_name = serializers.CharField(source='new_plan.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = SubscriptionChange
        fields = '__all__'
        read_only_fields = ('id', 'created_at')


class SubscriptionUsageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionUsage
        fields = '__all__'
        read_only_fields = ('id', 'recorded_at')


class SubscriptionSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    is_in_trial = serializers.BooleanField(read_only=True)

    class Meta:
        model = Subscription
        fields = '__all__'
        read_only_fields = ('id', 'subscription_number', 'current_period_start', 
                           'current_period_end', 'next_billing_date', 'created_at', 'updated_at')

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class SubscriptionListSerializer(serializers.ModelSerializer):
    """Simplified serializer for subscription listings"""
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    is_in_trial = serializers.BooleanField(read_only=True)

    class Meta:
        model = Subscription
        fields = ('id', 'subscription_number', 'customer_name', 'plan_name', 'status', 
                 'price', 'next_billing_date', 'is_in_trial', 'created_at')


class SubscriptionDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer with all related data"""
    customer = CustomerSerializer(read_only=True)
    plan = SubscriptionPlanSerializer(read_only=True)
    payment_method = StoredPaymentMethodSerializer(read_only=True)
    changes = SubscriptionChangeSerializer(many=True, read_only=True)
    usage_records = SubscriptionUsageSerializer(many=True, read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    is_in_trial = serializers.BooleanField(read_only=True)

    class Meta:
        model = Subscription
        fields = '__all__'
        read_only_fields = ('id', 'subscription_number', 'current_period_start', 
                           'current_period_end', 'next_billing_date', 'created_at', 'updated_at')