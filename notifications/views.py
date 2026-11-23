import hmac
import hashlib
import json

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import NotificationLog


@csrf_exempt
@require_POST
def provider_webhook(request, provider):
    secret = settings.NOTIFICATION_PROVIDER_WEBHOOK_SECRETS.get(provider, "")
    signature = (
        request.headers.get("X-Signature")
        or request.headers.get("X-Twilio-Signature")
        or request.headers.get("X-Hub-Signature-256")
        or ""
    )
    if not secret:
        return JsonResponse(
            {"detail": "Invalid signature.", "code": "invalid_signature"},
            status=403,
        )
    digest = hmac.new(
        secret.encode(),
        request.body,
        hashlib.sha256,
    ).hexdigest()
    provided = signature.removeprefix("sha256=")
    if not hmac.compare_digest(digest, provided):
        return JsonResponse(
            {"detail": "Invalid signature.", "code": "invalid_signature"},
            status=403,
        )
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        payload = {}
    message_id = (
        payload.get("MessageSid")
        or payload.get("messageId")
        or payload.get("messages", [{}])[0].get("id")
    )
    status_value = str(
        payload.get("Status")
        or payload.get("status")
        or payload.get("delivery_status")
        or ""
    ).upper()
    if not message_id:
        return JsonResponse({"detail": "Accepted."}, status=202)
    log = NotificationLog.objects.filter(
        provider_message_id=str(message_id),
    ).first()
    if log:
        if status_value in ("DELIVERED", "READ", "SUCCESS"):
            log.status = NotificationLog.Status.DELIVERED
        elif status_value in ("FAILED", "UNDELIVERABLE", "REJECTED"):
            log.status = NotificationLog.Status.FAILED
        log.save(update_fields=["status", "updated_at"])
    return JsonResponse({"detail": "Accepted."}, status=202)
