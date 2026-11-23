from django.core.cache import cache
from django.db import transaction

from .catalog import PERMISSION_CATALOG, SYSTEM_ROLE_TEMPLATES
from .models import (
    Permission,
    Role,
    RolePermission,
    Staff,
    StaffRoleAssignment,
)


@transaction.atomic
def sync_permissions():
    for code, description in PERMISSION_CATALOG.items():
        Permission.objects.update_or_create(
            code=code,
            defaults={
                "module": code.split(".", 1)[0],
                "description": description,
            },
        )

    for codename, template in SYSTEM_ROLE_TEMPLATES.items():
        role, _created = Role.objects.update_or_create(
            landlord=None,
            codename=codename,
            defaults={
                "name": template["name"],
                "is_system": True,
                "is_locked": template["locked"],
            },
        )
        role.role_permissions.exclude(
            permission_id__in=template["permissions"]
        ).delete()
        for code in template["permissions"]:
            RolePermission.objects.get_or_create(
                role=role,
                permission_id=code,
            )


@transaction.atomic
def clone_system_roles(landlord):
    seeded = set(
        Permission.objects.filter(
            code__in=PERMISSION_CATALOG
        ).values_list("code", flat=True)
    )
    missing = set(PERMISSION_CATALOG) - seeded
    if missing:
        raise RuntimeError("Permission catalog is not seeded")

    for codename, template in SYSTEM_ROLE_TEMPLATES.items():
        role = Role.objects.create(
            landlord=landlord,
            codename=codename,
            name=template["name"],
            is_system=False,
            is_locked=template["locked"],
        )
        for code in template["permissions"]:
            RolePermission.objects.create(
                role=role,
                permission_id=code,
            )
    return Role.objects.get(
        landlord=landlord,
        codename="OWNER",
    )


def bump_rbac_version(landlord_id):
    key = f"rbac:ver:{landlord_id}"
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=None)


def has_perm(staff, perm_code, org_unit):
    if staff is None or org_unit is None:
        return False
    if org_unit.landlord_id != staff.landlord_id:
        return False

    version = cache.get(
        f"rbac:ver:{staff.landlord_id}",
        0,
    )
    key = (
        f"rbac:perm:{staff.landlord_id}:{version}:"
        f"{staff.id}:{perm_code}:{org_unit.id}"
    )
    cached = cache.get(key)
    if cached is not None:
        return cached

    ancestor_ids = [
        value
        for value in org_unit.path.strip("/").split("/")
        if value
    ]
    permitted = StaffRoleAssignment.objects.filter(
        staff_id=staff.id,
        staff__status=Staff.Status.ACTIVE,
        staff__user__is_active=True,
        staff__landlord_id=staff.landlord_id,
        staff__landlord__status="ACTIVE",
        landlord_id=staff.landlord_id,
        org_unit_id__in=ancestor_ids,
        org_unit__landlord_id=staff.landlord_id,
        role__landlord_id__in=(None, staff.landlord_id),
        role__role_permissions__permission_id=perm_code,
    ).exists()

    cache.set(key, permitted, timeout=300)
    return permitted


@transaction.atomic
def assign_role(*, staff, role, org_unit, granted_by=None):
    if staff.landlord_id != org_unit.landlord_id:
        raise PermissionError("Cross-landlord org unit")
    if role.landlord_id not in (None, staff.landlord_id):
        raise PermissionError("Cross-landlord role")

    assignment = StaffRoleAssignment.objects.create(
        landlord_id=staff.landlord_id,
        staff=staff,
        role=role,
        org_unit=org_unit,
        granted_by=granted_by,
    )
    transaction.on_commit(
        lambda: bump_rbac_version(staff.landlord_id)
    )
    return assignment


@transaction.atomic
def revoke_role(*, assignment):
    landlord_id = assignment.landlord_id
    assignment.delete()
    transaction.on_commit(
        lambda: bump_rbac_version(landlord_id)
    )


def grant_role(*, grantor, staff, role, org_unit):
    if staff.landlord_id != grantor.landlord_id:
        raise PermissionError("Cross-landlord staff")
    if role.landlord_id not in (None, staff.landlord_id):
        raise PermissionError("Cross-landlord role")
    if not has_perm(grantor, "role.manage", org_unit):
        raise PermissionError("Permission denied")

    grantor_permissions = set(
        RolePermission.objects.filter(
            role__staff_assignments__staff=grantor
        ).values_list("permission_id", flat=True)
    )
    role_permissions = set(
        role.role_permissions.values_list("permission_id", flat=True)
    )
    if not role_permissions.issubset(grantor_permissions):
        raise PermissionError("Role escalation is forbidden")

    return assign_role(
        staff=staff,
        role=role,
        org_unit=org_unit,
        granted_by=grantor,
    )


@transaction.atomic
def change_role_permissions(*, role, permission_codes):
    RolePermission.objects.filter(role=role).exclude(
        permission_id__in=permission_codes
    ).delete()
    for code in permission_codes:
        RolePermission.objects.get_or_create(
            role=role,
            permission_id=code,
        )
    landlord_id = role.landlord_id
    if landlord_id is not None:
        transaction.on_commit(
            lambda: bump_rbac_version(landlord_id)
        )


@transaction.atomic
def suspend_or_remove_staff(*, staff, status, reason):
    if status not in (
        Staff.Status.SUSPENDED,
        Staff.Status.REMOVED,
    ):
        raise ValueError("Unsupported staff status")
    if len(reason.strip()) < 5:
        raise ValueError("A reason of at least 5 characters is required")

    staff.status = status
    staff.status_reason = reason
    staff.save(update_fields=["status", "status_reason"])
    landlord_id = staff.landlord_id
    transaction.on_commit(
        lambda: bump_rbac_version(landlord_id)
    )
