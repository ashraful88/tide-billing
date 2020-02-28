from django.contrib import admin

from . import models

class OrderItemInline(admin.TabularInline):
    model = models.Order_item

class OrderAdmin(admin.ModelAdmin):
	list_display = ("order_id", "customer", "order_date", "order_status")
	inlines = [
        OrderItemInline,
    ]

class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "product", "price")

class subscriptionProductAdmin(admin.ModelAdmin):
    list_display = ("title", "product", "customer", "start_date", "requiring_duration")

admin.site.register(models.Order, OrderAdmin)
admin.site.register(models.Order_status)
admin.site.register(models.Order_item, OrderItemAdmin)
admin.site.register(models.subscription_product, subscriptionProductAdmin)
admin.site.register(models.subscription_order)
