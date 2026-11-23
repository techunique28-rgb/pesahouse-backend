from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import LandlordMeView, OrgUnitViewSet

router = DefaultRouter()
router.register(r"", OrgUnitViewSet, basename="org-unit")

urlpatterns = [
    path("landlords/me/", LandlordMeView.as_view()),
    path("org-units/", include(router.urls)),
]
