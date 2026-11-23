from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TransactionTestCase

from accounts.services import DuplicateAccount, signup_tenant
from landlords.services import signup_landlord


class SignupSecurityTests(TransactionTestCase):
    def setUp(self):
        cache.clear()

    def test_duplicate_phone_is_generic(self):
        get_user_model().objects.create_user(
            phone_e164="+256700000001",
            password="StrongPass!123",
            full_name="One",
        )
        with self.assertRaises(DuplicateAccount) as raised:
            signup_tenant(
                phone="+256700000001",
                password="StrongPass!123",
                full_name="Two",
                email=None,
            )
        self.assertEqual(
            str(raised.exception),
            "Unable to create account.",
        )

    def test_blank_emails_do_not_collide(self):
        first = signup_tenant(
            phone="+256700000003",
            password="StrongPass!123",
            full_name="First",
            email="",
        )
        second = signup_tenant(
            phone="+256700000004",
            password="StrongPass!123",
            full_name="Second",
            email="   ",
        )
        self.assertIsNone(first.email)
        self.assertIsNone(second.email)

    def test_unseeded_permissions_fail_signup(self):
        with patch(
            "landlords.services.Permission.objects.values_list",
            return_value=[],
        ):
            with self.assertRaises(RuntimeError):
                signup_landlord(
                    phone="+256700000005",
                    password="StrongPass!123",
                    full_name="Owner",
                    email="owner@example.com",
                    landlord_name="Test Landlord",
                )

    @patch("landlords.services.notify")
    def test_nothing_sent_when_signup_rolls_back(self, notify):
        with patch(
            "landlords.services.create_join_code",
            side_effect=RuntimeError("forced failure"),
        ):
            with self.assertRaises(RuntimeError):
                signup_landlord(
                    phone="+256700000006",
                    password="StrongPass!123",
                    full_name="Owner",
                    email="owner@example.com",
                    landlord_name="Rollback Landlord",
                )
        notify.assert_not_called()
