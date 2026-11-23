from rest_framework import serializers

from .models import Landlord, OrgUnit


class LandlordSerializer(serializers.ModelSerializer):
    class Meta:
        model = Landlord
        fields = [
            "id",
            "name",
            "status",
            "require_tenant_approval",
            "created_at",
        ]
        read_only_fields = ["id", "status", "created_at"]


class OrgUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrgUnit
        fields = [
            "id",
            "landlord",
            "parent",
            "path",
            "depth",
            "kind",
            "name",
            "status",
            "require_tenant_approval",
            "created_at",
        ]
        read_only_fields = ["id", "landlord", "path", "depth", "created_at"]
