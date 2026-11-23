from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from notifications.services import notify
from .models import normalize_phone


LOGIN_FAILURES = "login_failures"


class DuplicateAccount(Exception):
    pass


def uniform_login_error():
    return "Phone or password is incorrect."


@transaction.atomic
def signup_tenant(*, phone, password, full_name, email=None):
    from .models import User

    phone = normalize_phone(phone)
    email = (
        email.strip().lower()
        if isinstance(email, str) and email.strip()
        else None
    )
    try:
        validate_password(password)
    except ValidationError as exc:
        raise ValueError(exc.messages[0]) from exc

    try:
        with transaction.atomic():
            user = User.objects.create_user(
                phone_e164=phone,
                password=password,
                full_name=full_name,
                email=email,
                is_phone_verified=False,
            )
    except IntegrityError as exc:
        raise DuplicateAccount("Unable to create account.") from exc

    transaction.on_commit(
        lambda: notify("OTP_SIGNUP", user, {})
    )
    return user


def login_user(phone, password):
    phone = normalize_phone(phone)
    lock_key = f"login_lock:{phone}"
    failures_key = f"{LOGIN_FAILURES}:{phone}"
    if cache.get(lock_key):
        raise PermissionError(uniform_login_error())

    user = authenticate(username=phone, password=password)
    if user is None or not user.is_active or not user.is_phone_verified:
        failures = cache.get(failures_key, 0) + 1
        cache.set(failures_key, failures, timeout=900)
        if failures >= 5:
            cache.set(lock_key, True, timeout=900)
        raise PermissionError(uniform_login_error())

    cache.delete(failures_key)
    refresh = RefreshToken.for_user(user)
    return refresh, refresh.access_token


def logout_refresh(refresh_token):
    try:
        RefreshToken(refresh_token).blacklist()
    except Exception as exc:
        raise ValueError("Invalid refresh token") from exc


def logout_all(user):
    tokens = OutstandingToken.objects.filter(user=user)
    for outstanding in tokens:
        try:
            RefreshToken(str(outstanding.token)).blacklist()
        except Exception:
            continue


@transaction.atomic
def password_change(user, old_password, new_password):
    if not user.check_password(old_password):
        raise PermissionError("Current password is incorrect")
    validate_password(new_password, user=user)
    user.set_password(new_password)
    user.save(update_fields=["password"])
    logout_all(user)
    transaction.on_commit(
        lambda: notify("PASSWORD_CHANGED", user, {})
    )
    return user
