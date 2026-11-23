from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from .tenant_context import clear_current_landlord, set_current_landlord


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        clear_current_landlord()
        try:
            if not request.path.startswith("/api/v1/"):
                return self.get_response(request)
            if request.path in (
                "/api/v1/health/",
                "/api/v1/accounts/login/",
                "/api/v1/accounts/signup/tenant/",
                "/api/v1/accounts/signup/landlord/",
                "/api/v1/accounts/verify-otp/",
                "/api/v1/accounts/resend-otp/",
                "/api/v1/accounts/password/reset/request/",
                "/api/v1/accounts/password/reset/confirm/",
                "/api/v1/tenants/join/",
            ):
                return self.get_response(request)

            header = request.headers.get("X-Landlord-Id")
            if not header:
                return self._forbidden()

            authorization = request.headers.get("Authorization", "")
            if not authorization.startswith("Bearer "):
                return self._forbidden()

            try:
                validated = JWTAuthentication().get_validated_token(
                    authorization.split(" ", 1)[1]
                )
                user = JWTAuthentication().get_user(validated)
            except (InvalidToken, Exception):
                return self._forbidden()

            if not getattr(user, "is_active", False):
                return self._forbidden()

            from landlords.models import Landlord
            from rbac.models import Staff
            from tenants.models import TenantProfile
            from .tenant_models import unscoped

            with unscoped("middleware: membership check"):
                try:
                    landlord = Landlord.objects.get(
                        id=header,
                        status="ACTIVE",
                    )
                except (Landlord.DoesNotExist, ValueError):
                    return self._forbidden()
                has_staff = Staff.all_objects.filter(
                    landlord_id=landlord.id,
                    user_id=user.id,
                    status="ACTIVE",
                ).exists()
                has_tenant = TenantProfile.all_objects.filter(
                    landlord_id=landlord.id,
                    user_id=user.id,
                    status__in=("PENDING", "ACTIVE"),
                ).exists()

            if not (has_staff or has_tenant):
                return self._forbidden()

            set_current_landlord(landlord.id)
            request.landlord_id = landlord.id
            request.staff = (
                Staff.all_objects.filter(
                    landlord_id=landlord.id,
                    user_id=user.id,
                    status="ACTIVE",
                ).first()
            )
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config("
                        "'app.landlord_id', %s, true)",
                        [str(landlord.id)],
                    )
            return self.get_response(request)
        finally:
            clear_current_landlord()

    @staticmethod
    def _forbidden():
        return JsonResponse(
            {"detail": "Forbidden.", "code": "permission_denied"},
            status=403,
        )
