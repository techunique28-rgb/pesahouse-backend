from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from notifications.services import notify
from .models import normalize_phone
from .otp import issue_otp, resend_locked, verify_otp
from .serializers import (
    LoginSerializer,
    MeSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    SignupTenantSerializer,
    VerifyOtpSerializer,
)
from .services import (
    login_user,
    logout_all,
    logout_refresh,
    password_change,
    signup_tenant,
)
from .throttles import (
    LoginThrottle,
    PasswordResetThrottle,
    ResendOtpThrottle,
    SignupThrottle,
    VerifyOtpThrottle,
)


class HealthView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"status": "ok"})


class SignupLandlordView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [SignupThrottle]

    def post(self, request):
        from landlords.services import signup_landlord
        serializer = SignupTenantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            data = serializer.validated_data
            user, landlord = signup_landlord(
                phone=data["phone"],
                password=data["password"],
                full_name=data["full_name"],
                email=data.get("email"),
                landlord_name=request.data.get("landlord_name", "PesaHouse"),
            )
        except (ValueError, Exception) as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "user_id": str(user.id),
                "landlord_id": str(landlord.id),
            },
            status=status.HTTP_201_CREATED,
        )


class SignupTenantView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [SignupThrottle]

    def post(self, request):
        serializer = SignupTenantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = signup_tenant(**serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"detail": "Verification code sent."}, status=201)


class VerifyOtpView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [VerifyOtpThrottle]

    def post(self, request):
        serializer = VerifyOtpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        phone = normalize_phone(data["phone"])
        user = get_user_model().objects.filter(phone_e164=phone).first()
        if not user or not verify_otp(data["purpose"], str(user.id), data["code"]):
            return Response(
                {"detail": "Invalid or expired verification code."},
                status=400,
            )
        User = get_user_model()
        user = User.objects.filter(phone_e164=phone).first()
        if user:
            if data["purpose"] in ("OTP_SIGNUP", "OTP_LOGIN", "OTP_CLAIM"):
                user.is_phone_verified = True
            user.save(update_fields=["is_phone_verified"])
        return Response({"detail": "Verified."})


class ResendOtpView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ResendOtpThrottle]

    def post(self, request):
        phone = normalize_phone(request.data.get("phone", ""))
        purpose = request.data.get("purpose", "OTP_SIGNUP")
        user = get_user_model().objects.filter(phone_e164=phone).first()
        if not user:
            return Response({"detail": "Verification code sent."})
        if resend_locked(purpose, str(user.id)):
            return Response({"detail": "Verification code sent."})
        issue_otp(purpose, str(user.id))
        notify(purpose, user, {})
        return Response({"detail": "Verification code sent."})


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [LoginThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            refresh, access = login_user(
                serializer.validated_data["phone"],
                serializer.validated_data["password"],
            )
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=401)
        return Response({
            "access": str(access),
            "refresh": str(refresh),
        })


class LogoutView(APIView):
    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return Response({"detail": "Refresh token is required."}, status=400)
        try:
            logout_refresh(refresh)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"detail": "Logged out."})


class LogoutAllView(APIView):
    def post(self, request):
        logout_all(request.user)
        return Response({"detail": "Logged out everywhere."})


class MeView(APIView):
    def get(self, request):
        return Response(MeSerializer(request.user).data)

    def patch(self, request):
        serializer = MeSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class AccountContextsView(APIView):
    def get(self, request):
        from rbac.models import Staff
        from tenants.models import TenantProfile

        staff = Staff.all_objects.filter(
            user=request.user,
            status="ACTIVE",
        ).select_related("landlord")
        tenants = TenantProfile.all_objects.filter(
            user=request.user,
            status__in=["PENDING", "ACTIVE"],
        ).select_related("landlord")
        return Response({
            "staff": [
                {
                    "landlord_id": str(row.landlord_id),
                    "landlord_name": row.landlord.name,
                }
                for row in staff
            ],
            "tenants": [
                {
                    "landlord_id": str(row.landlord_id),
                    "landlord_name": row.landlord.name,
                }
                for row in tenants
            ],
        })


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PasswordResetThrottle]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = normalize_phone(serializer.validated_data["phone"])
        user = get_user_model().objects.filter(phone_e164=phone).first()
        if user:
            issue_otp("OTP_RESET", str(user.id))
            notify("OTP_RESET", user, {})
        return Response({"detail": "If the account exists, a code was sent."})


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        phone = normalize_phone(data["phone"])
        user = get_user_model().objects.filter(phone_e164=phone).first()
        if not user or not verify_otp("OTP_RESET", str(user.id), data["code"]):
            return Response({"detail": "Invalid or expired code."}, status=400)
        user.set_password(data["new_password"])
        user.save(update_fields=["password"])
        logout_all(user)
        return Response({"detail": "Password reset."})


class PasswordChangeView(APIView):
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            password_change(
                request.user,
                serializer.validated_data["old_password"],
                serializer.validated_data["new_password"],
            )
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"detail": "Password changed."})


class ClaimView(APIView):
    def post(self, request):
        code = request.data.get("code")
        password = request.data.get("password")
        if not password:
            return Response({"detail": "Password is required."}, status=400)
        phone = normalize_phone(request.data.get("phone", ""))
        user = get_user_model().objects.filter(phone_e164=phone).first()
        if not user or not verify_otp("OTP_CLAIM", str(user.id), code):
            return Response({"detail": "Invalid or expired code."}, status=400)
        user.set_password(password)
        user.is_phone_verified = True
        user.save(update_fields=["password", "is_phone_verified"])
        return Response({"detail": "Account claimed."})


class EmailSendCodeView(APIView):
    def post(self, request):
        if not request.user.email:
            return Response({"detail": "Email is required."}, status=400)
        issue_otp("OTP_EMAIL", str(request.user.id))
        notify("OTP_SIGNUP", request.user, {})
        return Response({"detail": "Verification code sent."})


class EmailVerifyView(APIView):
    def post(self, request):
        code = request.data.get("code")
        if not request.user.email:
            return Response({"detail": "Invalid or expired code."}, status=400)
        if not verify_otp("OTP_EMAIL", str(request.user.id), code):
            return Response({"detail": "Invalid or expired code."}, status=400)
        request.user.is_email_verified = True
        request.user.save(update_fields=["is_email_verified"])
        return Response({"detail": "Email verified."})


class PhoneChangeRequestView(APIView):
    def post(self, request):
        phone = normalize_phone(request.data.get("phone", ""))
        issue_otp("OTP_PHONE_CHANGE", str(request.user.id))
        notify("OTP_LOGIN", request.user, {})
        cache.set(f"phone_change:{request.user.id}", phone, timeout=300)
        return Response({"detail": "Verification code sent."})


class PhoneChangeConfirmView(APIView):
    def post(self, request):
        phone = cache.get(f"phone_change:{request.user.id}")
        code = request.data.get("code")
        if not phone or not verify_otp(
            "OTP_PHONE_CHANGE",
            str(request.user.id),
            code,
        ):
            return Response({"detail": "Invalid or expired code."}, status=400)
        request.user.phone_e164 = phone
        request.user.is_phone_verified = True
        request.user.save(update_fields=["phone_e164", "is_phone_verified"])
        cache.delete(f"phone_change:{request.user.id}")
        return Response({"detail": "Phone changed."})


class SessionsView(APIView):
    def get(self, request):
        rows = OutstandingToken.objects.filter(user=request.user)
        return Response([
            {
                "id": str(row.id),
                "created_at": row.created_at,
                "expires_at": row.expires_at,
            }
            for row in rows
        ])

    def delete(self, request):
        token_id = request.query_params.get("id")
        row = OutstandingToken.objects.filter(
            id=token_id,
            user=request.user,
        ).first()
        if row:
            try:
                RefreshToken(str(row.token)).blacklist()
            except Exception:
                pass
        return Response({"detail": "Session revoked."})


class AccountDeleteRequestView(APIView):
    def post(self, request):
        from rbac.models import Staff
        active_owner_count = 0
        owner_assignments = Staff.all_objects.filter(
            user=request.user,
            status="ACTIVE",
        ).values_list("landlord_id", flat=True)
        for landlord_id in set(owner_assignments):
            active_owner_count += Staff.all_objects.filter(
                landlord_id=landlord_id,
                status="ACTIVE",
                staffroleassignment__role__codename="OWNER",
            ).count()
        if active_owner_count:
            return Response(
                {"detail": "Account deletion is refused while you are an Owner."},
                status=400,
            )
        request.user.deleted_at = timezone.now()
        request.user.is_active = False
        request.user.save(update_fields=["deleted_at", "is_active"])
        return Response({"detail": "Account deletion requested."})
