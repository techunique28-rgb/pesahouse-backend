from django.conf import settings
from django.db import models


class NotificationLog(models.Model):
    class Channel(models.TextChoices):
        SMS = "SMS", "SMS"
        WHATSAPP = "WHATSAPP", "WhatsApp"
        EMAIL = "EMAIL", "Email"
        CONSOLE = "CONSOLE", "Console"

    class Status(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        SENT = "SENT", "Sent"
        DELIVERED = "DELIVERED", "Delivered"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=__import__("uuid").uuid4)
    landlord = models.ForeignKey(
        "landlords.Landlord",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        db_index=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="notification_logs",
        db_index=True,
    )
    channel = models.CharField(max_length=16, choices=Channel.choices)
    purpose = models.CharField(max_length=64, db_index=True)
    recipient_masked = models.CharField(max_length=128)
    provider = models.CharField(max_length=64)
    provider_message_id = models.CharField(max_length=128, null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    error_code = models.CharField(max_length=128, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
