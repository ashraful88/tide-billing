from django.contrib import admin
from .models import Order, OrderItem, OrderHistory


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('total_price', 'product_name', 'product_sku')


class OrderHistoryInline(admin.TabularInline):
    model = OrderHistory
    extra = 0
    readonly_fields = ('changed_at',)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'customer', 'order_type', 'status', 'total_amount', 'created_at')
    list_filter = ('status', 'order_type', 'created_at')
    search_fields = ('order_number', 'customer__name', 'notes')
    ordering = ('-created_at',)
    readonly_fields = ('id', 'order_number', 'created_at', 'updated_at')
    inlines = [OrderItemInline, OrderHistoryInline]
    
    fieldsets = (
        ('Order Information', {
            'fields': ('order_number', 'customer', 'order_type', 'status')
        }),
        ('Pricing', {
            'fields': ('subtotal', 'tax_amount', 'discount_amount', 'shipping_amount', 'total_amount')
        }),
        ('Addresses', {
            'fields': ('shipping_address', 'billing_address')
        }),
        ('Additional Information', {
            'fields': ('notes',)
        }),
        ('Timestamps', {
            'fields': ('shipped_at', 'delivered_at')
        }),
        ('Metadata', {
            'fields': ('id', 'created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product_name', 'quantity', 'unit_price', 'total_price')
    list_filter = ('created_at',)
    search_fields = ('order__order_number', 'product_name', 'product_sku')
    readonly_fields = ('id', 'total_price', 'product_name', 'product_sku')


@admin.register(OrderHistory)
class OrderHistoryAdmin(admin.ModelAdmin):
    list_display = ('order', 'status_from', 'status_to', 'changed_by', 'changed_at')
    list_filter = ('status_from', 'status_to', 'changed_at')
    search_fields = ('order__order_number', 'notes')
    readonly_fields = ('id', 'changed_at')
