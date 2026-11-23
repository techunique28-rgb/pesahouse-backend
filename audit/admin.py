from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "landlord",
        "actor_user",
        "action",
        "target_type",
        "created_at",
    )
    readonly_fields = (
        "id",
        "landlord",
        "actor_user",
        "actor_staff",
        "action",
        "target_type",
        "target_id",
        "before",
        "after",
        "ip",
        "request_id",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
