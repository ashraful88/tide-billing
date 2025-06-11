from django.contrib import admin

# Register your models here.
from .models import Customer

class CustomerAdmin(admin.ModelAdmin):
	list_display = ("id", "name", "email", "phone")
	#prepopulated_fields = {"slug": ("name",)}

admin.site.register(Customer, CustomerAdmin)
