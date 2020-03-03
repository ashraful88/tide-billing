from django.contrib import admin
from . import models
# Register your models here.

class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_id','customer','order_status','order_date',)

admin.site.register(models.Order, OrderAdmin)

class OrderItemSubAdmin(admin.ModelAdmin):
    list_display = ('order','subscription','status')

admin.site.register(models.Order_item_subscription, OrderItemSubAdmin)

class OrderItemProductAdmin(admin.ModelAdmin):
    list_display = ('order','product','price','status',)

admin.site.register(models.Order_item_product, OrderItemProductAdmin)

class OrderStatusAdmin(admin.ModelAdmin):
    list_display = ('order_status',)

admin.site.register(models.Order_status, OrderStatusAdmin)
