from django.contrib import admin

from .models import (
    Permission,
    Role,
    RolePermission,
    Staff,
    StaffRoleAssignment,
)


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("code", "module", "description")
    search_fields = ("code", "module")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "codename", "landlord", "is_system", "is_locked")


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ("role", "permission")


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ("user", "landlord", "status", "job_title", "created_at")
    readonly_fields = ("id", "landlord", "created_at")


@admin.register(StaffRoleAssignment)
class StaffRoleAssignmentAdmin(admin.ModelAdmin):
    list_display = ("staff", "role", "org_unit", "landlord", "granted_by")
