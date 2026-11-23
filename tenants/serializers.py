from rest_framework import serializers

from .models import TenantProfile


class TenantProfileSerializer(serializers.ModelSerializer):
    can_transact = serializers.BooleanField(read_only=True)

    class Meta:
        model = TenantProfile
        fields = [
            "id",
            "user",
            "org_unit",
            "display_name",
            "status",
            "status_reason",
            "admitted_by",
            "join_code",
            "approved_by",
            "approved_at",
            "can_transact",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "status",
            "status_reason",
            "admitted_by",
            "join_code",
            "approved_by",
            "approved_at",
            "can_transact",
            "created_at",
        ]


class JoinResolveSerializer(serializers.Serializer):
    code = serializers.CharField(min_length=8, max_length=8)


class TenantJoinSerializer(serializers.Serializer):
    code = serializers.CharField(min_length=8, max_length=8)
    display_name = serializers.CharField(max_length=150)


class TenantTransitionSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=10, required=False)
    org_unit_id = serializers.UUIDField(required=False)
