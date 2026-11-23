from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from audit.services import write_audit
from core.tenant_context import use_landlord
from core.uuid_ids import new_uuid
from notifications.services import notify
from rbac.catalog import PERMISSION_CATALOG
from rbac.models import Permission, Staff, StaffRoleAssignment
from rbac.services import clone_system_roles
from .models import Landlord, OrgUnit, create_join_code


@transaction.atomic
def signup_landlord(*, phone, password, full_name, email, landlord_name):
    from accounts.models import User, normalize_phone
    from accounts.services import DuplicateAccount

    phone = normalize_phone(phone)
    email = (
        email.strip().lower()
        if isinstance(email, str) and email.strip()
        else None
    )
    try:
        validate_password(password)
    except ValidationError as exc:
        raise ValueError(exc.messages[0]) from exc

    try:
        with transaction.atomic():
            user = User.objects.create_user(
                phone_e164=phone,
                password=password,
                full_name=full_name,
                email=email,
                is_phone_verified=False,
            )
    except IntegrityError as exc:
        raise DuplicateAccount("Unable to create account.") from exc

    missing_permissions = set(PERMISSION_CATALOG) - set(
        Permission.objects.values_list("code", flat=True)
    )
    if missing_permissions:
        raise RuntimeError("Permission catalog is not seeded")

    landlord = Landlord.objects.create(name=landlord_name)
    with use_landlord(landlord.id):
        root_id = new_uuid()
        root = OrgUnit.objects.create(
            id=root_id,
            landlord_id=landlord.id,
            parent=None,
            path=f"/{root_id}/",
            depth=0,
            kind=OrgUnit.Kind.ROOT,
            name=landlord_name,
            require_tenant_approval=None,
        )
        owner_role = clone_system_roles(landlord)
        staff = Staff.objects.create(
            landlord_id=landlord.id,
            user=user,
            status=Staff.Status.ACTIVE,
            invited_by=None,
        )
        StaffRoleAssignment.objects.create(
            landlord_id=landlord.id,
            staff=staff,
            role=owner_role,
            org_unit=root,
            granted_by=staff,
        )
        create_join_code(
            landlord.id,
            root.id,
            label="Default",
            is_active=True,
            created_by=staff,
        )

    write_audit(
        landlord.id,
        user,
        staff,
        "landlord.create",
        "Landlord",
        str(landlord.id),
        None,
        {"name": landlord.name, "status": landlord.status},
    )
    transaction.on_commit(
        lambda: notify(
            "OTP_SIGNUP",
            user,
            {"landlord_id": str(landlord.id)},
        )
    )
    return user, landlord


@transaction.atomic
def create_landlord_for_existing_user(*, user, landlord_name):
    if not user.is_phone_verified:
        raise PermissionError("Phone verification is required")
    if not getattr(user, "is_active", True):
        raise PermissionError("Account is inactive")

    missing_permissions = set(PERMISSION_CATALOG) - set(
        Permission.objects.values_list("code", flat=True)
    )
    if missing_permissions:
        raise RuntimeError("Permission catalog is not seeded")

    landlord = Landlord.objects.create(name=landlord_name)
    with use_landlord(landlord.id):
        root_id = new_uuid()
        root = OrgUnit.objects.create(
            id=root_id,
            landlord_id=landlord.id,
            parent=None,
            path=f"/{root_id}/",
            depth=0,
            kind=OrgUnit.Kind.ROOT,
            name=landlord_name,
            require_tenant_approval=None,
        )
        owner_role = clone_system_roles(landlord)
        staff = Staff.objects.create(
            landlord_id=landlord.id,
            user=user,
            status=Staff.Status.ACTIVE,
        )
        StaffRoleAssignment.objects.create(
            landlord_id=landlord.id,
            staff=staff,
            role=owner_role,
            org_unit=root,
            granted_by=staff,
        )
        create_join_code(
            landlord.id,
            root.id,
            label="Default",
            is_active=True,
            created_by=staff,
        )

    write_audit(
        landlord.id,
        user,
        staff,
        "landlord.create",
        "Landlord",
        str(landlord.id),
        None,
        {"name": landlord.name, "status": landlord.status},
    )
    return user, landlord


@transaction.atomic
def update_landlord_settings(
    landlord_id,
    *,
    name=None,
    require_tenant_approval=None,
):
    with use_landlord(landlord_id):
        landlord = Landlord.objects.select_for_update().get(id=landlord_id)
        if name is not None:
            landlord.name = name
        if require_tenant_approval is not None:
            landlord.require_tenant_approval = require_tenant_approval
        landlord.save(
            update_fields=["name", "require_tenant_approval"]
        )
    return landlord


@transaction.atomic
def move_org_unit(*, org_unit_id, new_parent_id=None):
    from rbac.services import bump_rbac_version

    unit = OrgUnit.objects.select_for_update().get(id=org_unit_id)
    if unit.parent_id is None:
        raise ValueError("The root node cannot be moved")
    if new_parent_id is None:
        raise ValueError("A parent is required")
    parent = OrgUnit.objects.select_for_update().get(id=new_parent_id)
    if parent.landlord_id != unit.landlord_id:
        raise PermissionError("Cross-landlord org unit")

    old_path = unit.path
    if parent.path == old_path or old_path + "/" in parent.path + "/":
        raise ValueError("A cycle is not allowed")
    if parent.depth + 1 > 5:
        raise ValueError("Maximum organization depth is 5")

    descendants = OrgUnit.objects.select_for_update().filter(
        path__startswith=old_path
    )
    old_depth = unit.depth
    unit.parent = parent
    unit.depth = parent.depth + 1
    unit.path = f"{parent.path}{unit.id}/"
    unit.save(update_fields=["parent", "depth", "path"])

    for descendant in descendants.exclude(id=unit.id):
        relative = descendant.path[len(old_path):]
        descendant.depth = unit.depth + (
            descendant.depth - old_depth
        )
        descendant.path = unit.path + relative
        descendant.save(update_fields=["depth", "path"])

    transaction.on_commit(
        lambda: bump_rbac_version(unit.landlord_id)
    )
    return unit
