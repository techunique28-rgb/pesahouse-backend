import hashlib
import hmac

from django.conf import settings
from django.core.cache import cache


def otp_hash(code: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(),
        code.encode(),
        hashlib.sha256,
    ).hexdigest()


def issue_otp(purpose: str, user_id: str) -> None:
    cache.set(
        f"otp:{purpose}:{user_id}:resend",
        True,
        timeout=settings.OTP_RESEND_SECONDS,
    )


def verify_otp(purpose: str, user_id: str, code: str) -> bool:
    key = f"otp:{purpose}:{user_id}"
    payload = cache.get(key)
    if not payload:
        return False

    attempts = payload["attempts"] + 1
    if attempts > settings.OTP_ATTEMPTS:
        cache.delete(key)
        return False

    if hmac.compare_digest(payload["hash"], otp_hash(code)):
        cache.delete(key)
        cache.delete(f"{key}:resend")
        return True

    cache.set(
        key,
        {**payload, "attempts": attempts},
        timeout=settings.OTP_TTL_SECONDS,
    )
    return False


def resend_locked(purpose: str, user_id: str) -> bool:
    return cache.get(f"otp:{purpose}:{user_id}:resend") is not None
