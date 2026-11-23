from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    PublicJoinConfirmView,
    PublicJoinResolveView,
    TenantProfileViewSet,
)

router = DefaultRouter()
router.register(r"", TenantProfileViewSet, basename="tenant")

urlpatterns = [
    path("join/resolve/", PublicJoinResolveView.as_view(), name="join-resolve"),
    path("join/confirm/", PublicJoinConfirmView.as_view(), name="join-confirm"),
    path("", include(router.urls)),
]
