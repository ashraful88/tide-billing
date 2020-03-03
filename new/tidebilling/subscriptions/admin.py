from django.contrib import admin
from . import models
# Register your models here.

class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('title','price', 'service', 'status')

admin.site.register(models.Subscription_plans, SubscriptionPlanAdmin)

class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('title','customer','requiring_duration','status',)

admin.site.register(models.Subscription, SubscriptionAdmin)
