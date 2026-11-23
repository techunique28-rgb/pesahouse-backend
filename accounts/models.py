import phonenumbers
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import models
from django.db.models import Q

from core.uuid_ids import new_uuid
from .manager import UserManager


def normalize_phone(value):
    parsed = phonenumbers.parse(value, "UG")
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError("Invalid phone number")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


class User(AbstractBaseUser):
    class PreferredChannel(models.TextChoices):
        SMS = "SMS", "SMS"
        WHATSAPP = "WHATSAPP", "WhatsApp"
        EMAIL = "EMAIL", "Email"

    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    phone_e164 = models.CharField(
        max_length=16,
        unique=True,
        validators=[],
    )
    email = models.EmailField(null=True, blank=True)
    full_name = models.CharField(max_length=150)
    is_phone_verified = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_platform_admin = models.BooleanField(default=False)
    preferred_channel = models.CharField(
        max_length=10,
        choices=PreferredChannel.choices,
        default=PreferredChannel.SMS,
    )
    whatsapp_opt_in = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "phone_e164"
    REQUIRED_FIELDS = ["full_name"]

    objects = UserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["email"],
                condition=Q(email__isnull=False, deleted_at__isnull=True),
                name="accounts_user_unique_active_email",
            ),
            models.CheckConstraint(
                condition=(
                    Q(email__isnull=True)
                    | Q(email=models.functions.Lower("email"))
                ),
                name="accounts_user_email_lower",
            ),
            models.CheckConstraint(
                condition=Q(phone_e164__startswith="+"),
                name="accounts_user_phone_e164",
            ),
        ]
        indexes = [
            models.Index(fields=["phone_e164"]),
            models.Index(fields=["email"]),
            models.Index(fields=["deleted_at"]),
        ]

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        if self.phone_e164:
            self.phone_e164 = normalize_phone(self.phone_e164)
        super().save(*args, **kwargs)

    @property
    def is_staff(self):
        return self.is_platform_admin

    def has_perm(self, perm, obj=None):
        return bool(
            self.is_active
            and self.is_platform_admin
        )

    def has_module_perms(self, app_label):
        return bool(
            self.is_active
            and self.is_platform_admin
        )
