from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PaymentViewSet, RefundViewSet, StoredPaymentMethodViewSet

router = DefaultRouter()
router.register(r'payments', PaymentViewSet)
router.register(r'refunds', RefundViewSet)
router.register(r'payment-methods', StoredPaymentMethodViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
]