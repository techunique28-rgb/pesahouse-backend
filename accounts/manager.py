from django.contrib.auth.base_user import BaseUserManager
from django.db.models import Q


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, phone_e164, password=None, **extra_fields):
        if not phone_e164:
            raise ValueError("Phone number is required")
        phone_e164 = phone_e164.strip()
        email = extra_fields.get("email")
        if email:
            extra_fields["email"] = email.strip().lower()
        user = self.model(phone_e164=phone_e164, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_e164, password=None, **extra_fields):
        extra_fields.setdefault("is_platform_admin", True)
        extra_fields.setdefault("is_phone_verified", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("full_name", "Platform Administrator")
        return self.create_user(phone_e164, password, **extra_fields)
