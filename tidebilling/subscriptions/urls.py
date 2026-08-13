from rest_framework.routers import DefaultRouter
from .views import (
    SubscriptionPlanViewSet, SubscriptionViewSet, 
    SubscriptionChangeViewSet, SubscriptionUsageViewSet
)

router = DefaultRouter()
router.register(r'plans', SubscriptionPlanViewSet)
router.register(r'subscriptions', SubscriptionViewSet)
router.register(r'changes', SubscriptionChangeViewSet)
router.register(r'usage', SubscriptionUsageViewSet)

urlpatterns = router.urls
