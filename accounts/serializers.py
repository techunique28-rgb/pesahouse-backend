from rest_framework import serializers

from .models import User


class SignupTenantSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=16)
    password = serializers.CharField(write_only=True)
    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_null=True)


class VerifyOtpSerializer(serializers.Serializer):
    purpose = serializers.CharField(max_length=64)
    phone = serializers.CharField(max_length=16)
    code = serializers.RegexField(regex=r"^\d{6}$")


class LoginSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=16)
    password = serializers.CharField(write_only=True)


class MeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "phone_e164",
            "email",
            "full_name",
            "is_phone_verified",
            "is_email_verified",
            "preferred_channel",
            "whatsapp_opt_in",
        ]
        read_only_fields = [
            "id",
            "phone_e164",
            "is_phone_verified",
            "is_email_verified",
        ]


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)


class PasswordResetRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=16)


class PasswordResetConfirmSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=16)
    code = serializers.RegexField(regex=r"^\d{6}$")
    new_password = serializers.CharField(write_only=True)
