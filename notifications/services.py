import logging
import uuid
from django.core.cache import cache
from django.db import transaction
from django.conf import settings

from .models import NotificationLog
from .channels import mask_recipient
from .templates import render_template
from .tasks import send_notification

logger = logging.getLogger(__name__)


def notify(purpose: str, user, context: dict):
    safe_context = {
        key: value
        for key, value in context.items()
        if key not in {"otp", "password", "token"}
    }
    if purpose.startswith("OTP_"):
        message = "PesaHouse verification notification"
    else:
        message = render_template(purpose, safe_context)
    preferred = getattr(user, "preferred_channel", "SMS")
    if preferred == "WHATSAPP" and not getattr(user, "whatsapp_opt_in", False):
        preferred = "SMS"
    channel_map = {
        "SMS": "SMS",
        "WHATSAPP": "WHATSAPP",
        "EMAIL": "EMAIL",
    }
    channel = "CONSOLE"
    recipient = ""
    if settings.DEBUG:
        channel = "CONSOLE"
    else:
        channel = channel_map.get(preferred, "SMS")
        if preferred == "EMAIL":
            recipient = user.email or ""
        elif preferred == "WHATSAPP":
            recipient = user.phone_e164
        else:
            recipient = user.phone_e164

    recipient_masked = mask_recipient(recipient or str(user.phone_e164))
    purpose_hour = f"notify:recipient:{recipient_masked}:{purpose}:hour"
    daily = f"notify:user:{user.id}:day"
    if cache.get(purpose_hour, 0) >= settings.NOTIFICATION_ABUSE_PER_RECIPIENT_PURPOSE_HOUR:
        raise RuntimeError("Notification abuse limit exceeded")
    if cache.get(daily, 0) >= settings.NOTIFICATION_ABUSE_DAILY_PER_USER:
        raise RuntimeError("Notification daily limit exceeded")
    cache.set(purpose_hour, cache.get(purpose_hour, 0) + 1, timeout=3600)
    cache.set(daily, cache.get(daily, 0) + 1, timeout=86400)

    log = NotificationLog.objects.create(
        landlord_id=getattr(context, "landlord_id", None)
        if isinstance(context, dict) is False
        else context.get("landlord_id"),
        user=user,
        channel=channel,
        purpose=purpose,
        recipient_masked=recipient_masked,
        provider="console" if settings.DEBUG else preferred.lower(),
        status=NotificationLog.Status.QUEUED,
    )
    idempotency_key = str(uuid.uuid4())
    transaction.on_commit(
        lambda: send_notification.apply_async(
            kwargs={
                "notification_id": str(log.id),
                "recipient": recipient or str(user.phone_e164),
                "message": message,
                "purpose": purpose,
                "context": safe_context,
                "user_id": str(user.id),
                "idempotency_key": idempotency_key,
            },
            task_id=idempotency_key,
        )
    )
    logger.info(
        "Notification queued",
        extra={
            "notification_id": str(log.id),
            "landlord_id": getattr(log, "landlord_id", None),
            "user_id": str(user.id),
        },
    )
    return log
