from django.db import models
import uuid
import os

def image_file_path(instance, filename):
    """Generate file path for new image"""
    ext = filename.split('.')[-1]
    filename = f'{uuid.uuid4()}.{ext}'

    return os.path.join('uploads/products/', filename)

class Category(models.Model):
    title = models.CharField(max_length=200)
    cat_id = models.IntegerField(unique=True)
    slug = models.SlugField(max_length=200, unique=True)
    status = models.BooleanField(default=True)
    des = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def __unicode__(self):
        return self.title
    
    class Meta:
        verbose_name = "Category"
        verbose_name_plural = "Categories"

class SubCategory(models.Model):
    title = models.CharField(max_length=200)
    cat_id = models.IntegerField(unique=True)
    slug = models.SlugField(max_length=200, unique=True)
    status = models.BooleanField(default=True)
    des = models.TextField(blank=True)
    parent = models.ForeignKey(Category, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def __unicode__(self):
        return self.title
        
    class Meta:
        verbose_name = "Sub Category"
        verbose_name_plural = "Sub Categories"


class Tag(models.Model):
    slug = models.SlugField(max_length=200, unique=True)

    def __str__(self):
        return self.slug

    def __unicode__(self):
        return self.slug


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    sku = models.CharField(max_length=100, unique=True)
    qty = models.IntegerField(default=0)
    image = models.ImageField(null=True, upload_to=image_file_path)
    base_price = models.DecimalField(max_digits=5, decimal_places=2)
    price = models.DecimalField(max_digits=5, decimal_places=2)
    body = models.TextField()
    #requiring_duration = models.DurationField(default=0)
    slug = models.SlugField(max_length=200, unique=True)
    publish = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    category = models.ManyToManyField(Category)
    tags = models.ManyToManyField(Tag)

    def __str__(self):
        return self.title

    def __unicode__(self):
        return self.title

