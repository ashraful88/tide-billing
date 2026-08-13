from rest_framework import serializers
from .models import ServiceCategory, Service, ServiceRequest, ServiceDeliverable, TimeLog, ServiceFeedback
from customers.serializers import CustomerSerializer


class ServiceCategorySerializer(serializers.ModelSerializer):
    service_count = serializers.SerializerMethodField()

    class Meta:
        model = ServiceCategory
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')

    def get_service_count(self, obj):
        return obj.services.filter(is_active=True).count()


class ServiceSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = Service
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at')


class ServiceDeliverableSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceDeliverable
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at')


class TimeLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = TimeLog
        fields = '__all__'
        # `user` is set by TimeLogViewSet.perform_create from the request; as a
        # writable field it was both required (blocking creation) and a way to
        # log time against another user.
        read_only_fields = ('id', 'hours', 'user', 'created_at', 'updated_at')


class ServiceFeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceFeedback
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at')


class ServiceRequestSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    service_name = serializers.CharField(source='service.name', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to.username', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = ServiceRequest
        fields = '__all__'
        read_only_fields = ('id', 'request_number', 'actual_hours', 'created_at', 'updated_at',
                           'submitted_at', 'started_at', 'completed_at')

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class ServiceRequestListSerializer(serializers.ModelSerializer):
    """Simplified serializer for service request listings"""
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    service_name = serializers.CharField(source='service.name', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to.username', read_only=True)

    class Meta:
        model = ServiceRequest
        fields = ('id', 'request_number', 'title', 'customer_name', 'service_name', 
                 'status', 'priority', 'assigned_to_name', 'estimated_cost', 'created_at')


class ServiceRequestDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer with all related data"""
    customer = CustomerSerializer(read_only=True)
    service = ServiceSerializer(read_only=True)
    deliverables = ServiceDeliverableSerializer(many=True, read_only=True)
    time_logs = TimeLogSerializer(many=True, read_only=True)
    feedback = ServiceFeedbackSerializer(read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to.username', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = ServiceRequest
        fields = '__all__'
        read_only_fields = ('id', 'request_number', 'actual_hours', 'created_at', 'updated_at',
                           'submitted_at', 'started_at', 'completed_at')