from django.test import SimpleTestCase, override_settings

from notifications.tasks import generate_otp


class SignupOtpSecurityTests(SimpleTestCase):
    @override_settings(SECRET_KEY="test-secret")
    def test_generate_otp_is_repeatable_and_returns_no_plaintext_in_task_args(self):
        from django.core.cache import cache

        cache.clear()
        first = generate_otp("OTP_SIGNUP", "user-123")
        second = generate_otp("OTP_SIGNUP", "user-123")
        self.assertEqual(first, second)
        self.assertRegex(first, r"^\d{6}$")
        payload = cache.get("otp:OTP_SIGNUP:user-123")
        self.assertNotIn("code", payload)
        self.assertEqual(len(payload["hash"]), 64)

    def test_duplicate_account_error_is_generic(self):
        from accounts.services import DuplicateAccount

        error = DuplicateAccount("Unable to create account.")
        self.assertEqual(str(error), "Unable to create account.")

    @override_settings(SECRET_KEY="test-secret")
    def test_task_arguments_and_rendered_context_contain_no_otp(self):
        task_kwargs = {
            "notification_id": "notification-1",
            "recipient": "+256700000000",
            "message": "PesaHouse verification notification",
            "purpose": "OTP_SIGNUP",
            "context": {"landlord_id": "landlord-1"},
            "user_id": "user-1",
        }
        self.assertNotIn("otp", task_kwargs)
        self.assertNotIn("otp", task_kwargs["context"])

    @override_settings(DEBUG=True)
    def test_notify_queues_no_otp_and_does_not_log_it(self):
        from unittest.mock import Mock, patch

        from django.core.cache import cache
        from notifications.services import notify

        cache.clear()
        user = Mock()
        user.id = "user-2"
        user.phone_e164 = "+256700000000"
        user.preferred_channel = "SMS"
        user.whatsapp_opt_in = False

        queued_callback = []
        with (
            patch(
                "notifications.services.NotificationLog.objects.create",
                return_value=Mock(id="notification-2", landlord_id=None),
            ),
            patch(
                "notifications.services.transaction.on_commit",
                side_effect=lambda callback: queued_callback.append(callback),
            ),
            patch(
                "notifications.services.send_notification.apply_async"
            ) as apply_async,
            self.assertLogs("notifications", level="INFO") as logs,
        ):
            notify("OTP_SIGNUP", user, {"otp": "928104"})
            queued_callback[0]()

        kwargs = apply_async.call_args.kwargs["kwargs"]
        self.assertNotIn("928104", repr(kwargs))
        self.assertNotIn("otp", kwargs["context"])
        self.assertNotIn("928104", "\n".join(logs.output))
