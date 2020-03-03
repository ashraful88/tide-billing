from django.contrib import admin
from . import models
# Register your models here.
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('title','unit_price','status',)

admin.site.register(models.Service, ServiceAdmin)
