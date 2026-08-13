from rest_framework import serializers
from .models import Customer, CustomerContact


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'
        read_only_fields = ('id', 'is_archived', 'archived_at', 'created', 'modified')

    def validate_email(self, value):
        if Customer.objects.filter(email=value).exclude(pk=self.instance.pk if self.instance else None).exists():
            raise serializers.ValidationError("A customer with this email already exists.")
        return value


class CustomerContactSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)

    class Meta:
        model = CustomerContact
        fields = '__all__'
        read_only_fields = ('id', 'created', 'modified')


class CustomerListSerializer(serializers.ModelSerializer):
    """Simplified serializer for customer listings"""
    contact_count = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = ('id', 'cus_id', 'name', 'email', 'phone', 'status', 'created', 'contact_count')

    def get_contact_count(self, obj):
        return obj.customercontact_set.count()


class CustomerDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer with related contacts"""
    contacts = CustomerContactSerializer(source='customercontact_set', many=True, read_only=True)
    
    class Meta:
        model = Customer
        fields = '__all__'
        read_only_fields = ('id', 'created', 'modified')