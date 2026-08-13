from rest_framework.routers import DefaultRouter
from .views import (
    ServiceCategoryViewSet, ServiceViewSet, ServiceRequestViewSet,
    ServiceDeliverableViewSet, TimeLogViewSet, ServiceFeedbackViewSet
)

router = DefaultRouter()
router.register(r'categories', ServiceCategoryViewSet)
router.register(r'services', ServiceViewSet)
router.register(r'requests', ServiceRequestViewSet)
router.register(r'deliverables', ServiceDeliverableViewSet)
router.register(r'time-logs', TimeLogViewSet)
router.register(r'feedback', ServiceFeedbackViewSet)

urlpatterns = router.urls
