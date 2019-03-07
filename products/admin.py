from django.contrib import admin

from . import models

class ProductAdmin(admin.ModelAdmin):
	list_display = ("title", "base_price", "sku")
	prepopulated_fields = {"slug": ("title",)}

class CategoryAdmin(admin.ModelAdmin):
	list_display = ("title", "parent")
	prepopulated_fields = {"slug": ("title",)}

admin.site.register(models.Category, CategoryAdmin)
admin.site.register(models.Tag)
admin.site.register(models.Product, ProductAdmin)
