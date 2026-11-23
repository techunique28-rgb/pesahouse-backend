from django.contrib import admin

from .models import JoinCode, Landlord, OrgUnit


@admin.register(Landlord)
class LandlordAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "require_tenant_approval", "created_at")
    readonly_fields = ("id", "created_at")


@admin.register(OrgUnit)
class OrgUnitAdmin(admin.ModelAdmin):
    list_display = ("name", "landlord", "kind", "depth", "status")
    readonly_fields = ("id", "landlord", "path", "depth", "created_at")


@admin.register(JoinCode)
class JoinCodeAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "landlord",
        "org_unit",
        "is_active",
        "uses",
        "max_uses",
        "expires_at",
    )
    readonly_fields = ("id", "code", "uses", "created_at", "revoked_at")
