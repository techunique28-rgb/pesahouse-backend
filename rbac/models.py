import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from core.tenant_models import TenantModel


class Permission(models.Model):
    code = models.CharField(max_length=60, primary_key=True)
    module = models.CharField(max_length=60)
    description = models.CharField(max_length=255)

    class Meta:
        indexes = [
            models.Index(fields=["module"]),
        ]


class RoleManager(models.Manager):
    def get_queryset(self):
        from core.tenant_context import get_current_landlord
        landlord_id = get_current_landlord()
        queryset = super().get_queryset()
        if landlord_id is None:
            return queryset.filter(landlord__isnull=True)
        return queryset.filter(
            Q(landlord__isnull=True) | Q(landlord_id=landlord_id)
        )


class Role(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    landlord = models.ForeignKey(
        "landlords.Landlord",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="custom_roles",
    )
    codename = models.CharField(max_length=40)
    name = models.CharField(max_length=150)
    is_system = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)

    objects = RoleManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["landlord", "codename"],
                condition=Q(landlord__isnull=False),
                name="role_unique_landlord_codename",
            ),
            models.UniqueConstraint(
                fields=["codename"],
                condition=Q(landlord__isnull=True),
                name="role_unique_system_codename",
            ),
        ]
        indexes = [
            models.Index(fields=["landlord"]),
            models.Index(fields=["codename"]),
        ]


class RolePermission(models.Model):
    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name="role_permissions",
    )
    permission = models.ForeignKey(
        Permission,
        on_delete=models.CASCADE,
        related_name="+",
    )

    class Meta:
        unique_together = ("role", "permission")
        indexes = [
            models.Index(fields=["role"]),
            models.Index(fields=["permission"]),
        ]


class Staff(TenantModel):
    class Status(models.TextChoices):
        INVITED = "INVITED", "Invited"
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"
        REMOVED = "REMOVED", "Removed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="staff_memberships",
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.INVITED,
        db_index=True,
    )
    status_reason = models.TextField(blank=True)
    job_title = models.CharField(max_length=150, blank=True)
    invited_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["landlord", "id"],
                name="staff_unique_landlord_id",
            ),
            models.UniqueConstraint(
                fields=["user", "landlord"],
                condition=~Q(status="REMOVED"),
                name="staff_unique_active_user_landlord",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status__in=["SUSPENDED", "REMOVED"])
                    | Q(status_reason__length__gte=5)
                ),
                name="staff_status_reason_length",
            ),
        ]
        indexes = [
            models.Index(fields=["landlord", "user"]),
            models.Index(fields=["landlord", "status"]),
            models.Index(fields=["user"]),
        ]


class StaffRoleAssignment(TenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name="role_assignments",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name="staff_assignments",
    )
    org_unit = models.ForeignKey(
        "landlords.OrgUnit",
        on_delete=models.PROTECT,
        related_name="role_assignments",
    )
    granted_by = models.ForeignKey(
        Staff,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["staff", "role", "org_unit"],
                name="assignment_unique_staff_role_node",
            ),
        ]
        indexes = [
            models.Index(fields=["landlord", "staff"]),
            models.Index(fields=["landlord", "role"]),
            models.Index(fields=["landlord", "org_unit"]),
        ]
