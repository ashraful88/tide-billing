from django.contrib import admin

# Register your models here.
from . import models

class CustomerAdmin(admin.ModelAdmin):
	list_display = ("cus_id", "name", "email", "phone")
	#prepopulated_fields = {"slug": ("name",)}

class CustomerContactAdmin(admin.ModelAdmin):
    list_display = ('id','name', 'email', 'phone')
    #prepopulated_fields = {"slug": ("name",)}


admin.site.register(models.CustomerContact, CustomerContactAdmin)
admin.site.register(models.Customer, CustomerAdmin)

