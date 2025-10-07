from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CustomerViewSet, CustomerContactViewSet

router = DefaultRouter()
router.register(r'customers', CustomerViewSet)
router.register(r'contacts', CustomerContactViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
]