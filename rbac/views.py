from rest_framework import mixins, permissions, viewsets
from rest_framework.response import Response
from rest_framework.decorators import action

from .models import Permission, Role, Staff
from .serializers import (
    PermissionSerializer,
    RoleSerializer,
    StaffSerializer,
)


class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Permission.objects.all().order_by("code")
    serializer_class = PermissionSerializer
    permission_classes = [permissions.IsAuthenticated]


class RoleViewSet(viewsets.ModelViewSet):
    serializer_class = RoleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Role.objects.all()


class StaffViewSet(viewsets.ModelViewSet):
    serializer_class = StaffSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Staff.objects.select_related("user")

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        staff = self.get_object()
        reason = request.data.get("reason", "")
        if len(reason.strip()) < 5:
            return Response(
                {"detail": "A reason of at least 5 characters is required."},
                status=400,
            )
        staff.status = Staff.Status.SUSPENDED
        staff.status_reason = reason
        staff.save(update_fields=["status", "status_reason"])
        return Response(self.get_serializer(staff).data)

    @action(detail=True, methods=["post"])
    def remove(self, request, pk=None):
        staff = self.get_object()
        reason = request.data.get("reason", "")
        if len(reason.strip()) < 5:
            return Response(
                {"detail": "A reason of at least 5 characters is required."},
                status=400,
            )
        staff.status = Staff.Status.REMOVED
        staff.status_reason = reason
        staff.save(update_fields=["status", "status_reason"])
        return Response(self.get_serializer(staff).data)
