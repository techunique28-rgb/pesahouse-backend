from django.contrib import admin

from .models import TenantProfile, TenantStatusHistory


@admin.register(TenantProfile)
class TenantProfileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "landlord",
        "user",
        "org_unit",
        "status",
        "created_at",
    )
    readonly_fields = (
        "id",
        "landlord",
        "user",
        "org_unit",
        "display_name",
        "status",
        "status_reason",
        "national_id_key",
        "admitted_by",
        "join_code",
        "approved_by",
        "approved_at",
        "created_at",
    )


@admin.register(TenantStatusHistory)
class TenantStatusHistoryAdmin(admin.ModelAdmin):
    readonly_fields = (
        "id",
        "landlord",
        "tenant_profile",
        "from_status",
        "to_status",
        "reason",
        "changed_by",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
