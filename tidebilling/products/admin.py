from django.contrib import admin

from products import models

# Register your models here.
class ProductAdmin(admin.ModelAdmin):
	list_display = ("title", "base_price", "sku")
	prepopulated_fields = {"slug": ("title",)}

class CategoryAdmin(admin.ModelAdmin):
	list_display = ("title", "cat_id")
	prepopulated_fields = {"slug": ("title",)}

class SubCategoryAdmin(admin.ModelAdmin):
    list_display = ('title','parent', 'cat_id')
    prepopulated_fields = {"slug": ("title",)}

admin.site.register(models.SubCategory, SubCategoryAdmin)
admin.site.register(models.Category, CategoryAdmin)
admin.site.register(models.Tag)
admin.site.register(models.Product, ProductAdmin)
