from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import TenantProfile, TenantStatusHistory
from .serializers import (
    JoinResolveSerializer,
    TenantJoinSerializer,
    TenantProfileSerializer,
    TenantTransitionSerializer,
)
from .services import (
    InvalidJoinCode,
    TenantJoinNotAllowed,
    add_tenant,
    approve_tenant,
    evict_tenant,
    join_with_code,
    reject_tenant,
    resolve_join_code,
    shift_tenant,
    signed_national_id_url,
    upload_national_id,
)


class PublicJoinResolveView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = JoinResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = resolve_join_code(serializer.validated_data["code"])
        if result is None:
            return Response(
                {"detail": "Join code is invalid or unavailable."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({
            "landlord_name": result["landlord_name"],
            "org_unit_name": result["org_unit_name"],
        })


class PublicJoinConfirmView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = TenantJoinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            profile = join_with_code(
                request.user,
                serializer.validated_data["code"],
                serializer.validated_data["display_name"],
            )
        except (InvalidJoinCode, TenantJoinNotAllowed):
            return Response(
                {
                    "detail": "Join request could not be completed.",
                    "code": "join_unavailable",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            TenantProfileSerializer(profile).data,
            status=status.HTTP_201_CREATED,
        )


class TenantProfileViewSet(viewsets.ModelViewSet):
    serializer_class = TenantProfileSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = TenantProfile.objects.select_related(
            "user",
            "org_unit",
        )
        status_value = self.request.query_params.get("status")
        if status_value:
            queryset = queryset.filter(status=status_value)
        return queryset

    def create(self, request):
        serializer = TenantTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from accounts.models import User
        user_id = request.data.get("user_id")
        org_unit_id = serializer.validated_data.get("org_unit_id")
        display_name = request.data.get("display_name")
        if not user_id or not org_unit_id or not display_name:
            return Response(
                {"detail": "user_id, org_unit_id and display_name are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from landlords.models import OrgUnit
        try:
            user = User.objects.get(id=user_id)
            org_unit = OrgUnit.objects.get(id=org_unit_id)
            profile = add_tenant(
                org_unit.landlord_id,
                org_unit,
                user,
                display_name,
                request.user,
                getattr(request, "staff", None),
            )
        except (User.DoesNotExist, OrgUnit.DoesNotExist, ValueError,
                PermissionError) as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            TenantProfileSerializer(profile).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        profile = get_object_or_404(self.get_queryset(), id=pk)
        actor_staff = getattr(request, "staff", None)
        result = approve_tenant(
            profile.id,
            request.user,
            actor_staff,
        )
        return Response(TenantProfileSerializer(result).data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        serializer = TenantTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = get_object_or_404(self.get_queryset(), id=pk)
        result = reject_tenant(
            profile.id,
            serializer.validated_data["reason"],
            request.user,
            getattr(request, "staff", None),
        )
        return Response(TenantProfileSerializer(result).data)

    @action(detail=True, methods=["post"], url_path="shift")
    def shift(self, request, pk=None):
        serializer = TenantTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = get_object_or_404(self.get_queryset(), id=pk)
        result = shift_tenant(
            profile.id,
            serializer.validated_data["org_unit_id"],
            serializer.validated_data["reason"],
            request.user,
            getattr(request, "staff", None),
        )
        return Response(TenantProfileSerializer(result).data)

    @action(detail=True, methods=["post"], url_path="evict")
    def evict(self, request, pk=None):
        serializer = TenantTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = get_object_or_404(self.get_queryset(), id=pk)
        result = evict_tenant(
            profile.id,
            serializer.validated_data["reason"],
            request.user,
            getattr(request, "staff", None),
        )
        return Response(TenantProfileSerializer(result).data)

    @action(detail=True, methods=["get"], url_path="history")
    def history(self, request, pk=None):
        profile = get_object_or_404(self.get_queryset(), id=pk)
        rows = TenantStatusHistory.objects.filter(
            tenant_profile=profile
        ).values(
            "id",
            "from_status",
            "to_status",
            "reason",
            "changed_by",
            "created_at",
        )
        return Response(list(rows))

    @action(detail=True, methods=["post"], url_path="national-id")
    def national_id(self, request, pk=None):
        profile = get_object_or_404(self.get_queryset(), id=pk)
        uploaded = request.FILES.get("file")
        if uploaded is None:
            return Response(
                {"detail": "A file is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            key = upload_national_id(
                profile.id,
                uploaded,
                getattr(request, "staff", None),
            )
        except (ValueError, PermissionError) as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"national_id_key": key})

    @action(detail=True, methods=["get"], url_path="national-id/link")
    def national_id_link(self, request, pk=None):
        profile = get_object_or_404(self.get_queryset(), id=pk)
        try:
            url = signed_national_id_url(
                profile.id,
                getattr(request, "staff", None),
            )
        except (ValueError, PermissionError) as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"url": url, "expires_in": 300})
