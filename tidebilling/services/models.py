from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
import uuid

from customers.models import Customer


class ServiceCategory(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Service Categories"
        ordering = ['name']

    def __str__(self):
        return self.name


class Service(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField()
    category = models.ForeignKey(ServiceCategory, on_delete=models.CASCADE, related_name='services')
    
    # Pricing
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_recurring = models.BooleanField(default=False)
    billing_frequency = models.CharField(max_length=20, choices=[
        ('hourly', 'Hourly'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('annually', 'Annually'),
        ('one_time', 'One Time'),
    ], default='one_time')
    
    # Service details
    estimated_hours = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    deliverables = models.TextField(blank=True)
    requirements = models.TextField(blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ServiceRequest(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('on_hold', 'On Hold'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_number = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='service_requests')
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    
    # Request details
    title = models.CharField(max_length=300)
    description = models.TextField()
    requirements = models.TextField(blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Timeline
    requested_start_date = models.DateField(null=True, blank=True)
    requested_completion_date = models.DateField(null=True, blank=True)
    estimated_hours = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    actual_hours = models.DecimalField(max_digits=6, decimal_places=1, default=Decimal('0.0'))
    
    # Pricing
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    final_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Assignment
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_requests')
    
    # Attachments and notes
    attachments = models.JSONField(default=list, blank=True)  # Store file paths
    internal_notes = models.TextField(blank=True)
    client_notes = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_requests')

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['request_number']),
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Request {self.request_number} - {self.title}"

    def save(self, *args, **kwargs):
        if not self.request_number:
            # Generate request number
            from django.utils import timezone
            now = timezone.now()
            self.request_number = f"REQ-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)


class ServiceDeliverable(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service_request = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='deliverables')
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    due_date = models.DateField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Files
    file_path = models.CharField(max_length=500, blank=True)
    file_size = models.PositiveIntegerField(null=True, blank=True)  # in bytes
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['due_date', 'created_at']

    def __str__(self):
        return f"{self.service_request.request_number} - {self.title}"


class TimeLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service_request = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='time_logs')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    # Time tracking
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    hours = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    # Description
    description = models.TextField()
    is_billable = models.BooleanField(default=True)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_time']

    def __str__(self):
        return f"{self.service_request.request_number} - {self.user.username} - {self.hours}h"

    def save(self, *args, **kwargs):
        if self.start_time and self.end_time and not self.hours:
            # Calculate hours from start and end time
            duration = self.end_time - self.start_time
            self.hours = Decimal(str(duration.total_seconds() / 3600))
        super().save(*args, **kwargs)


class ServiceFeedback(models.Model):
    RATING_CHOICES = [
        (1, '1 - Poor'),
        (2, '2 - Fair'),
        (3, '3 - Good'),
        (4, '4 - Very Good'),
        (5, '5 - Excellent'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service_request = models.OneToOneField(ServiceRequest, on_delete=models.CASCADE, related_name='feedback')
    
    # Ratings
    overall_rating = models.PositiveIntegerField(choices=RATING_CHOICES)
    quality_rating = models.PositiveIntegerField(choices=RATING_CHOICES, null=True, blank=True)
    timeliness_rating = models.PositiveIntegerField(choices=RATING_CHOICES, null=True, blank=True)
    communication_rating = models.PositiveIntegerField(choices=RATING_CHOICES, null=True, blank=True)
    
    # Comments
    positive_feedback = models.TextField(blank=True)
    improvement_suggestions = models.TextField(blank=True)
    additional_comments = models.TextField(blank=True)
    
    # Recommendation
    would_recommend = models.BooleanField(null=True, blank=True)
    would_use_again = models.BooleanField(null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Feedback for {self.service_request.request_number} - {self.overall_rating}/5"
