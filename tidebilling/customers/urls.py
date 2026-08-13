from rest_framework.routers import DefaultRouter
from .views import CustomerViewSet, CustomerContactViewSet

router = DefaultRouter()
router.register(r'customers', CustomerViewSet)
router.register(r'contacts', CustomerContactViewSet)

urlpatterns = router.urls
