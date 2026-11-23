from django.contrib import admin

from .models import NotificationLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "landlord",
        "channel",
        "purpose",
        "recipient_masked",
        "status",
        "attempts",
        "created_at",
    )
    readonly_fields = (
        "recipient_masked",
        "provider",
        "provider_message_id",
        "status",
        "attempts",
        "error_code",
        "created_at",
        "updated_at",
    )
