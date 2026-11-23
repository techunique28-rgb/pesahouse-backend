import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from core.tenant_models import TenantModel


class TenantProfile(TenantModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACTIVE = "ACTIVE", "Active"
        SHIFTED = "SHIFTED", "Shifted"
        EVICTED = "EVICTED", "Evicted"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="tenant_profiles",
    )
    org_unit = models.ForeignKey(
        "landlords.OrgUnit",
        on_delete=models.PROTECT,
        related_name="tenant_profiles",
    )
    display_name = models.CharField(max_length=150)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    status_reason = models.TextField(blank=True)
    national_id_key = models.TextField(null=True, blank=True)
    admitted_by = models.ForeignKey(
        "rbac.Staff",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    join_code = models.ForeignKey(
        "landlords.JoinCode",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    approved_by = models.ForeignKey(
        "rbac.Staff",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["landlord", "id"],
                name="tenant_profile_unique_landlord_id",
            ),
            models.UniqueConstraint(
                fields=["user", "landlord"],
                condition=Q(status__in=["PENDING", "ACTIVE"]),
                name="tenant_profile_active_user_landlord",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status__in=["EVICTED", "REJECTED"])
                    | Q(status_reason__length__gte=10)
                ),
                name="tenant_profile_reason_length",
            ),
        ]
        indexes = [
            models.Index(fields=["landlord", "status"]),
            models.Index(fields=["landlord", "org_unit"]),
            models.Index(fields=["landlord", "user"]),
        ]

    @property
    def can_transact(self):
        return self.status == self.Status.ACTIVE


class TenantStatusHistory(TenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_profile = models.ForeignKey(
        TenantProfile,
        on_delete=models.PROTECT,
        related_name="status_history",
    )
    from_status = models.CharField(
        max_length=10,
        choices=TenantProfile.Status.choices,
        null=True,
        blank=True,
    )
    to_status = models.CharField(
        max_length=10,
        choices=TenantProfile.Status.choices,
    )
    reason = models.TextField(blank=True)
    changed_by = models.ForeignKey(
        "rbac.Staff",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["landlord", "tenant_profile"]),
            models.Index(fields=["landlord", "to_status"]),
            models.Index(fields=["landlord", "created_at"]),
        ]
