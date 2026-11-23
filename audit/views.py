from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        from core.tenant_context import get_current_landlord
        landlord_id = get_current_landlord()
        queryset = AuditLog.objects.all()
        if landlord_id is None:
            return queryset.none()
        queryset = queryset.filter(landlord_id=landlord_id)
        action = self.request.query_params.get("action")
        target_type = self.request.query_params.get("target_type")
        if action:
            queryset = queryset.filter(action=action)
        if target_type:
            queryset = queryset.filter(target_type=target_type)
        return queryset
