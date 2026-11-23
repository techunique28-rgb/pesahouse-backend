from django.urls import path

from .views import provider_webhook

urlpatterns = [
    path(
        "webhooks/<str:provider>/",
        provider_webhook,
        name="notification-provider-webhook",
    ),
]
