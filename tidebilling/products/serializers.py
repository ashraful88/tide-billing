from rest_framework import serializers
from .models import Product, Category, SubCategory, Tag


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = '__all__'


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'
        read_only_fields = ('created', 'modified')


class SubCategorySerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source='parent.title', read_only=True)

    class Meta:
        model = SubCategory
        fields = '__all__'
        read_only_fields = ('created', 'modified')


class ProductSerializer(serializers.ModelSerializer):
    category_names = serializers.StringRelatedField(source='category', many=True, read_only=True)
    tag_names = serializers.StringRelatedField(source='tags', many=True, read_only=True)

    class Meta:
        model = Product
        fields = '__all__'
        read_only_fields = ('id', 'created', 'modified')

    def validate_sku(self, value):
        if Product.objects.filter(sku=value).exclude(pk=self.instance.pk if self.instance else None).exists():
            raise serializers.ValidationError("A product with this SKU already exists.")
        return value


class ProductListSerializer(serializers.ModelSerializer):
    """Simplified serializer for product listings"""
    category_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ('id', 'title', 'sku', 'price', 'qty', 'publish', 'created', 'category_count')

    def get_category_count(self, obj):
        return obj.category.count()


class ProductDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer with related data"""
    categories = CategorySerializer(source='category', many=True, read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    
    class Meta:
        model = Product
        fields = '__all__'
        read_only_fields = ('id', 'created', 'modified')