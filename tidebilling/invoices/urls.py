from rest_framework.routers import DefaultRouter
from .views import InvoiceViewSet, InvoiceItemViewSet

router = DefaultRouter()
router.register(r'invoices', InvoiceViewSet)
router.register(r'invoice-items', InvoiceItemViewSet)

urlpatterns = router.urls
