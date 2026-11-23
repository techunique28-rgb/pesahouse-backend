from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import OrgUnit
from .serializers import LandlordSerializer, OrgUnitSerializer
from .services import update_landlord_settings


class LandlordMeView(APIView):
    def get(self, request):
        landlord_id = getattr(request, "landlord_id", None)
        if not landlord_id:
            return Response({"detail": "Forbidden."}, status=403)
        from .models import Landlord
        landlord = Landlord.objects.get(id=landlord_id)
        return Response(LandlordSerializer(landlord).data)

    def patch(self, request):
        landlord_id = getattr(request, "landlord_id", None)
        if not landlord_id:
            return Response({"detail": "Forbidden."}, status=403)
        serializer = LandlordSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        landlord = update_landlord_settings(
            landlord_id,
            name=serializer.validated_data.get("name"),
            require_tenant_approval=serializer.validated_data.get(
                "require_tenant_approval"
            ),
        )
        return Response(LandlordSerializer(landlord).data)


class OrgUnitViewSet(viewsets.ModelViewSet):
    serializer_class = OrgUnitSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return OrgUnit.objects.select_related("parent")

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        from .services import move_org_unit
        new_parent_id = request.data.get("parent_id")
        try:
            unit = move_org_unit(
                org_unit_id=pk,
                new_parent_id=new_parent_id,
            )
        except (ValueError, PermissionError) as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(OrgUnitSerializer(unit).data)
