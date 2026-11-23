from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = [
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
        ]
        read_only_fields = fields
