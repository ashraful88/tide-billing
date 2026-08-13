from django.contrib import admin
from .models import Product, Category, SubCategory, Tag


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('title', 'cat_id', 'status', 'created', 'modified')
    list_filter = ('status', 'created', 'modified')
    search_fields = ('title', 'des')
    ordering = ('title',)
    prepopulated_fields = {'slug': ('title',)}


@admin.register(SubCategory)
class SubCategoryAdmin(admin.ModelAdmin):
    list_display = ('title', 'parent', 'cat_id', 'status', 'created')
    list_filter = ('parent', 'status', 'created')
    search_fields = ('title', 'des', 'parent__title')
    ordering = ('parent__title', 'title')
    prepopulated_fields = {'slug': ('title',)}


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('slug',)
    search_fields = ('slug',)
    ordering = ('slug',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('title', 'sku', 'price', 'base_price', 'qty', 'publish', 'created')
    list_filter = ('publish', 'created', 'modified', 'category')
    search_fields = ('title', 'sku', 'body')
    ordering = ('-created',)
    readonly_fields = ('id', 'created', 'modified')
    filter_horizontal = ('category', 'tags')
    prepopulated_fields = {'slug': ('title',)}
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'slug', 'sku', 'body')
        }),
        ('Pricing & Inventory', {
            'fields': ('base_price', 'price', 'qty')
        }),
        ('Media', {
            'fields': ('image',)
        }),
        ('Categorization', {
            'fields': ('category', 'tags')
        }),
        ('Publishing', {
            'fields': ('publish',)
        }),
        ('Metadata', {
            'fields': ('id', 'created', 'modified'),
            'classes': ('collapse',)
        })
    )
