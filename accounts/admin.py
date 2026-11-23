from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class PesaHouseUserAdmin(UserAdmin):
    ordering = ("phone_e164",)
    list_display = (
        "phone_e164",
        "full_name",
        "email",
        "is_active",
        "is_phone_verified",
        "is_platform_admin",
    )
    list_filter = (
        "is_active",
        "is_phone_verified",
        "is_platform_admin",
    )
    fieldsets = (
        (None, {"fields": ("phone_e164", "password")}),
        ("Personal info", {"fields": ("full_name", "email")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_phone_verified",
                    "is_email_verified",
                    "is_platform_admin",
                    "preferred_channel",
                    "whatsapp_opt_in",
                    "deleted_at",
                )
            },
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "phone_e164",
                    "full_name",
                    "password1",
                    "password2",
                ),
            },
        ),
    )
