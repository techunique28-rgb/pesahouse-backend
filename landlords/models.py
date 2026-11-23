import re
import secrets
import uuid

from django.conf import settings
from django.db import IntegrityError, models
from django.db.models import Q
from django.db.models.functions import Lower

from core.tenant_models import TenantModel


JOIN_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


class Landlord(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"
        CLOSED = "CLOSED", "Closed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    require_tenant_approval = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["status"])]


class OrgUnit(TenantModel):
    class Kind(models.TextChoices):
        ROOT = "ROOT", "Root"
        DIVISION = "DIVISION", "Division"
        BRANCH = "BRANCH", "Branch"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        ARCHIVED = "ARCHIVED", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    path = models.TextField(unique=True)
    depth = models.PositiveSmallIntegerField()
    kind = models.CharField(max_length=10, choices=Kind.choices)
    name = models.CharField(max_length=150)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    require_tenant_approval = models.BooleanField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["landlord", "id"],
                name="orgunit_unique_landlord_id",
            ),
            models.UniqueConstraint(
                fields=["landlord"],
                condition=Q(parent__isnull=True),
                name="orgunit_one_root",
            ),
            models.CheckConstraint(
                condition=Q(depth__gte=0, depth__lte=5),
                name="orgunit_depth_range",
            ),
            models.CheckConstraint(
                condition=(
                    Q(parent__isnull=True, depth=0, kind="ROOT")
                    | ~Q(parent__isnull=True)
                ),
                name="orgunit_root_shape",
            ),
            models.UniqueConstraint(
                Lower("name"),
                fields=["landlord", "parent"],
                name="orgunit_unique_sibling_name",
            ),
        ]
        indexes = [
            models.Index(fields=["landlord", "parent"]),
            models.Index(fields=["landlord", "status"]),
            models.Index(fields=["landlord", "kind"]),
            models.Index(fields=["path"]),
        ]


class JoinCode(TenantModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org_unit = models.ForeignKey(
        OrgUnit,
        on_delete=models.PROTECT,
        related_name="join_codes",
    )
    code = models.CharField(max_length=8, unique=True)
    label = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    uses = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        "rbac.Staff",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(code__length=8),
                name="joincode_code_length",
            ),
            models.CheckConstraint(
                condition=Q(uses__gte=0),
                name="joincode_uses_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(max_uses__isnull=True) | Q(uses__lte=models.F("max_uses")),
                name="joincode_uses_limit",
            ),
        ]
        indexes = [
            models.Index(fields=["landlord", "org_unit"]),
            models.Index(fields=["landlord", "is_active"]),
            models.Index(fields=["expires_at"]),
        ]


def generate_join_code():
    return "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(8))


def create_join_code(landlord_id, org_unit_id, **kwargs):
    for _ in range(8):
        code = generate_join_code()
        try:
            return JoinCode.objects.create(
                landlord_id=landlord_id,
                org_unit_id=org_unit_id,
                code=code,
                **kwargs,
            )
        except IntegrityError:
            continue
    raise RuntimeError("Could not generate a unique join code")
