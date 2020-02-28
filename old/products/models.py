from __future__ import unicode_literals
import uuid
from django.db import models

# Create your models here.
class Category(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    publish = models.BooleanField(default=True)
    parent = models.IntegerField()

    def __str__(self):
        return self.title

        class Meta:
            verbose_name = "Category"
	    verbose_name_plural = "Categories"
	    ordering = ["parent"]

class Tag(models.Model):
    slug = models.SlugField(max_length=200, unique=True)

    def __str__(self):
        return self.slug

class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    sku = models.CharField(max_length=100, unique=True)
    qty = models.IntegerField(default=0)
    #image = models.ImageField(upload_to='images/%Y/%m/%d')
    base_price = models.FloatField()
    body = models.TextField()
    requiring_duration = models.DurationField(default=0)
    slug = models.SlugField(max_length=200, unique=True)
    publish = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    category = models.ManyToManyField(Category)
    tags = models.ManyToManyField(Tag)
    #objects = ProductQuerySet.as_manager()

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("product_detail", kwargs={"slug": self.slug})
