from unittest.mock import Mock, patch

import httpx
from django.test import SimpleTestCase, override_settings

from notifications.channels import SendResult, WhatsAppCloud
from notifications.tasks import send_notification
from notifications.templates import WHATSAPP_TEMPLATE_REGISTRY


class WhatsAppTemplateMappingTests(SimpleTestCase):
    def test_every_notification_purpose_has_a_template_mapping(self):
        from notifications.templates import TEMPLATE_REGISTRY

        self.assertEqual(set(TEMPLATE_REGISTRY), set(WHATSAPP_TEMPLATE_REGISTRY))

    def test_template_payload_contains_registered_name_language_and_variables(self):
        response = httpx.Response(
            200,
            json={"messages": [{"id": "wamid.test"}]},
            request=httpx.Request(
                "POST",
                "https://graph.facebook.com/v22.0/phone/messages",
            ),
        )
        with override_settings(
            WHATSAPP_PHONE_NUMBER_ID="phone",
            WHATSAPP_ACCESS_TOKEN="token",
            WHATSAPP_API_VERSION="v22.0",
        ), patch("notifications.channels.httpx.post", return_value=response) as post:
            result = WhatsAppCloud().send(
                "+256700000000",
                "unused text",
                purpose="OTP_SIGNUP",
                context={"otp": "123456"},
            )

        self.assertTrue(result.success)
        sent_payload = post.call_args.kwargs["json"]
        self.assertEqual(sent_payload["type"], "template")
        self.assertEqual(sent_payload["template"]["name"], "pesahouse_otp_signup")
        self.assertEqual(sent_payload["template"]["language"], {"code": "en"})
        self.assertEqual(
            sent_payload["template"]["components"],
            [{
                "type": "body",
                "parameters": [{"type": "text", "text": "123456"}],
            }],
        )
        self.assertNotIn("text", sent_payload)

    def test_unregistered_purpose_falls_back_at_channel_layer(self):
        with override_settings(
            WHATSAPP_PHONE_NUMBER_ID="phone",
            WHATSAPP_ACCESS_TOKEN="token",
        ):
            result = WhatsAppCloud().send(
                "+256700000000",
                "A free-form fallback message",
                purpose="UNKNOWN_PURPOSE",
                context={},
            )
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "template_not_registered")

    @patch("notifications.tasks.cache")
    @patch("notifications.tasks.AfricasTalkingSMS")
    @patch("notifications.tasks.WhatsAppCloud")
    def test_unknown_whatsapp_template_falls_back_to_next_sms_channel(
        self,
        whatsapp_class,
        sms_class,
        cache,
    ):
        whatsapp_class.return_value.send.return_value = SendResult(
            False,
            error_code="template_not_registered",
        )
        sms_class.return_value.name = "africastalking"
        sms_class.return_value.send.return_value = SendResult(True, "sms-id")
        cache.get.return_value = False

        log = Mock()
        log.id = "11111111-1111-1111-1111-111111111111"
        log.status = "QUEUED"
        log.channel = "WHATSAPP"
        log.attempts = 0
        log.save = Mock()

        with override_settings(DEBUG=False), patch(
            "notifications.tasks.NotificationLog.objects.get",
            return_value=log,
        ):
            send_notification.run(
                notification_id=str(log.id),
                recipient="+256700000000",
                message="Fallback SMS",
                idempotency_key="idem-1",
                purpose="UNKNOWN_PURPOSE",
                context={},
            )

        whatsapp_class.return_value.send.assert_called_once()
        sms_class.return_value.send.assert_called_once()
        self.assertEqual(log.status, "SENT")
