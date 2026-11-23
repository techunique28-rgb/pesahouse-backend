from rest_framework import serializers

from .models import Permission, Role, RolePermission, Staff


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["code", "module", "description"]
        read_only_fields = ["code", "module", "description"]


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = [
            "id",
            "landlord",
            "codename",
            "name",
            "is_system",
            "is_locked",
        ]
        read_only_fields = ["id", "landlord", "is_system"]


class StaffSerializer(serializers.ModelSerializer):
    class Meta:
        model = Staff
        fields = [
            "id",
            "landlord",
            "user",
            "status",
            "status_reason",
            "job_title",
            "invited_by",
            "created_at",
        ]
        read_only_fields = ["id", "landlord", "created_at"]
