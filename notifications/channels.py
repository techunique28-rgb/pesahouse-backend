from dataclasses import dataclass

import httpx
from django.conf import settings
from django.core.mail import EmailMultiAlternatives


@dataclass(frozen=True)
class SendResult:
    success: bool
    provider_message_id: str | None = None
    error_code: str | None = None


class NotificationChannel:
    name = "base"

    def send(
        self,
        recipient: str,
        message: str,
        purpose: str | None = None,
        context: dict | None = None,
    ) -> SendResult:
        raise NotImplementedError


class AfricasTalkingSMS(NotificationChannel):
    name = "africastalking"

    def send(
        self,
        recipient: str,
        message: str,
        purpose: str | None = None,
        context: dict | None = None,
    ) -> SendResult:
        try:
            response = httpx.post(
                "https://api.africastalking.com/version1/messaging",
                auth=(
                    settings.AFRICASTALKING_USERNAME,
                    settings.AFRICASTALKING_API_KEY,
                ),
                data={
                    "username": settings.AFRICASTALKING_USERNAME,
                    "to": recipient,
                    "message": message,
                    "from": settings.AFRICASTALKING_SENDER_ID,
                },
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
            recipients = payload.get("SMSMessageData", {}).get("Recipients", [])
            if recipients and recipients[0].get("status") == "Success":
                return SendResult(True, recipients[0].get("messageId"))
            return SendResult(False, error_code="provider_rejected")
        except httpx.HTTPError as exc:
            return SendResult(False, error_code=exc.__class__.__name__)


class TwilioSMS(NotificationChannel):
    name = "twilio"

    def send(
        self,
        recipient: str,
        message: str,
        purpose: str | None = None,
        context: dict | None = None,
    ) -> SendResult:
        if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
            return SendResult(False, error_code="missing_provider_credentials")
        try:
            response = httpx.post(
                (
                    "https://api.twilio.com/2010-04-01/Accounts/"
                    f"{settings.TWILIO_ACCOUNT_SID}/Messages.json"
                ),
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                data={
                    "To": recipient,
                    "From": settings.TWILIO_FROM_NUMBER,
                    "Body": message,
                },
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
            return SendResult(True, payload.get("sid"))
        except httpx.HTTPError as exc:
            return SendResult(False, error_code=exc.__class__.__name__)


class WhatsAppCloud(NotificationChannel):
    name = "whatsapp"

    def send(
        self,
        recipient: str,
        message: str,
        purpose: str | None = None,
        context: dict | None = None,
    ) -> SendResult:
        if not settings.WHATSAPP_PHONE_NUMBER_ID or not settings.WHATSAPP_ACCESS_TOKEN:
            return SendResult(False, error_code="missing_provider_credentials")
        from .templates import WHATSAPP_TEMPLATE_REGISTRY

        template = WHATSAPP_TEMPLATE_REGISTRY.get(purpose)
        if template is None:
            return SendResult(False, error_code="template_not_registered")

        context = context or {}
        missing = [name for name in template.variables if name not in context]
        if missing:
            return SendResult(False, error_code="missing_template_variables")

        parameters = [
            {"type": "text", "text": str(context[name])}
            for name in template.variables
        ]
        url = (
            f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/"
            f"{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        )
        try:
            response = httpx.post(
                url,
                headers={
                    "Authorization": "Bearer "
                    + settings.WHATSAPP_ACCESS_TOKEN,
                },
                json={
                    "messaging_product": "whatsapp",
                    "to": recipient,
                    "type": "template",
                    "template": {
                        "name": template.name,
                        "language": {"code": template.language},
                        "components": (
                            [{
                                "type": "body",
                                "parameters": parameters,
                            }]
                            if parameters
                            else []
                        ),
                    },
                },
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
            messages = payload.get("messages", [])
            message_id = messages[0].get("id") if messages else None
            return SendResult(True, message_id)
        except httpx.HTTPError as exc:
            return SendResult(False, error_code=exc.__class__.__name__)


class DjangoEmail(NotificationChannel):
    name = "email"

    def send(
        self,
        recipient: str,
        message: str,
        purpose: str | None = None,
        context: dict | None = None,
    ) -> SendResult:
        email = EmailMultiAlternatives(
            subject="PesaHouse notification",
            body=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
        )
        try:
            email.send(fail_silently=False)
            return SendResult(True)
        except Exception as exc:
            return SendResult(False, error_code=exc.__class__.__name__)


class ConsoleChannel(NotificationChannel):
    name = "console"

    def send(
        self,
        recipient: str,
        message: str,
        purpose: str | None = None,
        context: dict | None = None,
    ) -> SendResult:
        import logging

        logging.getLogger("notifications").info(
            "Console notification",
            extra={
                "recipient_masked": mask_recipient(recipient),
                "message_length": len(message),
            },
        )
        return SendResult(True, provider_message_id="console")


def mask_recipient(value: str) -> str:
    if "@" in value:
        local, domain = value.rsplit("@", 1)
        return f"{local[:2]}***@{domain}"
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) <= 4:
        return "***"
    return f"{digits[:3]}***{digits[-2:]}"
