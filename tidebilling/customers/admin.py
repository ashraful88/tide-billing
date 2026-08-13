from django.contrib import admin
from .models import Customer, CustomerContact


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'status', 'created', 'modified')
    list_filter = ('status', 'created', 'modified')
    search_fields = ('name', 'email', 'phone', 'cus_id')
    ordering = ('-created',)
    readonly_fields = ('id', 'created', 'modified')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('cus_id', 'name', 'email', 'phone', 'landline')
        }),
        ('Additional Details', {
            'fields': ('note', 'status')
        }),
        ('Metadata', {
            'fields': ('id', 'created', 'modified'),
            'classes': ('collapse',)
        })
    )


@admin.register(CustomerContact)
class CustomerContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'customer', 'created')
    list_filter = ('created', 'modified')
    search_fields = ('name', 'email', 'phone', 'customer__name')
    ordering = ('-created',)
    readonly_fields = ('id', 'created', 'modified')
    
    fieldsets = (
        ('Contact Information', {
            'fields': ('name', 'email', 'phone', 'homephone', 'landline')
        }),
        ('Association', {
            'fields': ('customer',)
        }),
        ('Metadata', {
            'fields': ('id', 'created', 'modified'),
            'classes': ('collapse',)
        })
    )
from .models import Customer

class CustomerAdmin(admin.ModelAdmin):
	list_display = ("id", "name", "email", "phone")
	#prepopulated_fields = {"slug": ("name",)}

admin.site.register(Customer, CustomerAdmin)
