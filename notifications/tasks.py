import hashlib
import hmac
import logging
import secrets

from celery import shared_task
from django.conf import settings
from django.core.cache import cache

from .models import NotificationLog
from .channels import (
    AfricasTalkingSMS,
    ConsoleChannel,
    DjangoEmail,
    TwilioSMS,
    WhatsAppCloud,
)

logger = logging.getLogger(__name__)


def otp_key(purpose: str, user_id: str) -> str:
    return f"otp:{purpose}:{user_id}"


def generate_otp(purpose: str, user_id: str) -> str:
    key = otp_key(purpose, user_id)
    existing = cache.get(key)
    nonce = (
        bytes.fromhex(existing["nonce"])
        if existing is not None
        else secrets.token_bytes(32)
    )
    code = str(int.from_bytes(
        hmac.new(
            settings.SECRET_KEY.encode(),
            nonce + f"{user_id}:{purpose}".encode(),
            hashlib.sha256,
        ).digest(),
        "big",
    ) % 1000000).zfill(6)
    hmac_hash = hmac.new(
        settings.SECRET_KEY.encode(),
        code.encode(),
        hashlib.sha256,
    ).hexdigest()
    if existing is not None:
        if not hmac.compare_digest(existing["hash"], hmac_hash):
            raise RuntimeError("OTP cache integrity mismatch")
        return code

    cache.set(
        key,
        {
            "hash": hmac_hash,
            "nonce": nonce.hex(),
            "attempts": 0,
        },
        timeout=settings.OTP_TTL_SECONDS,
    )
    cache.set(
        f"{key}:resend",
        True,
        timeout=settings.OTP_RESEND_SECONDS,
    )
    return code


@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def send_notification(
    self,
    notification_id: str,
    recipient: str,
    message: str,
    idempotency_key: str,
    purpose: str | None = None,
    context: dict | None = None,
    user_id: str | None = None,
) -> str:
    log = NotificationLog.objects.get(id=notification_id)
    if log.status == NotificationLog.Status.SENT:
        return idempotency_key

    log.attempts = min(log.attempts + 1, 32767)
    log.save(update_fields=["attempts", "updated_at"])

    channel_context = dict(context or {})
    if purpose and purpose.startswith("OTP_") and user_id:
        otp_code = generate_otp(purpose, user_id)
        channel_context["otp"] = otp_code
        from .templates import render_template
        message = render_template(purpose, channel_context)

    if settings.DEBUG:
        channels = [ConsoleChannel()]
    elif log.channel == "WHATSAPP":
        channels = [WhatsAppCloud(), AfricasTalkingSMS(), TwilioSMS()]
    elif log.channel == "EMAIL":
        channels = [DjangoEmail()]
    elif log.channel == "SMS":
        channels = [AfricasTalkingSMS(), TwilioSMS()]
    else:
        channels = [ConsoleChannel()]

    for channel in channels:
        if log.attempts > 1 and cache.get(
            f"notification:idem:{idempotency_key}:{channel.name}",
            False,
        ):
            continue
        result = channel.send(
            recipient,
            message,
            purpose=purpose,
            context=channel_context,
        )
        cache.set(
            f"notification:idem:{idempotency_key}:{channel.name}",
            True,
            timeout=86400,
        )
        if result.success:
            log.status = NotificationLog.Status.SENT
            log.provider = channel.name
            log.provider_message_id = result.provider_message_id
            log.error_code = None
            log.save(update_fields=[
                "status",
                "provider",
                "provider_message_id",
                "error_code",
                "updated_at",
            ])
            return idempotency_key

    log.status = NotificationLog.Status.FAILED
    log.error_code = "all_channels_failed"
    log.save(update_fields=["status", "error_code", "updated_at"])
    if log.attempts < 3:
        raise self.retry(exc=RuntimeError("all_channels_failed"), countdown=60)
    return idempotency_key
