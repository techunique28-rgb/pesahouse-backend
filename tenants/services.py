import mimetypes
import time
import uuid

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import F, Q
from django.utils import timezone

from audit.services import write_audit
from core.tenant_context import use_landlord
from landlords.models import JoinCode, Landlord, OrgUnit
from notifications.services import notify
from rbac.models import Staff, StaffRoleAssignment
from rbac.services import has_perm
from .selectors import approver_users
from .models import TenantProfile, TenantStatusHistory


class InvalidJoinCode(Exception):
    message = "Join code is invalid or unavailable."

    def __init__(self):
        super().__init__(self.message)


class TenantJoinNotAllowed(Exception):
    message = "Unable to complete the join request."

    def __init__(self):
        super().__init__(self.message)


def lock_valid_join_code(code: str) -> JoinCode:
    normalized = code.strip().upper()
    from core.tenant_models import unscoped

    with unscoped("join-code resolve and lock by submitted code"):
        join = (
            JoinCode.all_objects.select_for_update()
            .filter(code=normalized)
            .first()
        )
    now = timezone.now()
    if (
        join is None
        or not join.is_active
        or join.revoked_at is not None
        or (join.expires_at is not None and join.expires_at <= now)
        or (
            join.max_uses is not None
            and join.uses >= join.max_uses
        )
    ):
        raise InvalidJoinCode
    return join


def resolve_join_code(code: str):
    normalized = code.strip().upper()
    from core.tenant_models import unscoped

    with unscoped("join-code resolve: narrow public lookup"):
        join = (
            JoinCode.all_objects.select_related("landlord", "org_unit")
            .filter(code=normalized, is_active=True)
            .first()
        )
        if not join:
            return None
        if join.revoked_at is not None:
            return None
        if join.expires_at is not None and join.expires_at <= timezone.now():
            return None
        if join.max_uses is not None and join.uses >= join.max_uses:
            return None
        return {
            "landlord_name": join.landlord.name,
            "org_unit_name": join.org_unit.name,
        }


def join_with_code(user, code: str, display_name: str):
    display_name = " ".join(display_name.split())
    if not display_name:
        raise TenantJoinNotAllowed
    if not user.is_phone_verified:
        raise TenantJoinNotAllowed

    for attempt in range(5):
        try:
            return _join_with_locked_code(user, code, display_name)
        except InvalidJoinCode:
            existing = _existing_join_profile(user, code)
            if existing is not None:
                return existing
            raise
        except OperationalError:
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))


def _existing_join_profile(user, code):
    normalized = code.strip().upper()
    from core.tenant_models import unscoped

    with unscoped("join-code duplicate membership lookup"):
        join = JoinCode.all_objects.select_related(
            "landlord",
            "org_unit",
        ).filter(code=normalized).first()
        if (
            join is None
            or not join.is_active
            or join.revoked_at is not None
            or (
                join.expires_at is not None
                and join.expires_at <= timezone.now()
            )
        ):
            return None
        if (
            join.landlord.status != Landlord.Status.ACTIVE
            or join.org_unit.status != OrgUnit.Status.ACTIVE
        ):
            return None
        with use_landlord(join.landlord_id):
            active_owner_exists = StaffRoleAssignment.objects.filter(
                landlord_id=join.landlord_id,
                org_unit__kind=OrgUnit.Kind.ROOT,
                role__codename="OWNER",
                staff__status=Staff.Status.ACTIVE,
            ).exists()
            verified_owner_exists = StaffRoleAssignment.objects.filter(
                landlord_id=join.landlord_id,
                org_unit__kind=OrgUnit.Kind.ROOT,
                role__codename="OWNER",
                staff__status=Staff.Status.ACTIVE,
                staff__user__is_active=True,
                staff__user__is_phone_verified=True,
            ).exists()
            unverified_owner_exists = StaffRoleAssignment.objects.filter(
                landlord_id=join.landlord_id,
                org_unit__kind=OrgUnit.Kind.ROOT,
                role__codename="OWNER",
                staff__status=Staff.Status.ACTIVE,
                staff__user__is_active=True,
                staff__user__is_phone_verified=False,
            ).exists()
            if (
                not active_owner_exists
                or not verified_owner_exists
                or unverified_owner_exists
            ):
                return None
            return TenantProfile.objects.filter(
                landlord_id=join.landlord_id,
                user=user,
                status__in=[
                    TenantProfile.Status.PENDING,
                    TenantProfile.Status.ACTIVE,
                ],
            ).first()


def _join_with_locked_code(user, code, display_name):
    with transaction.atomic():
        join = lock_valid_join_code(code)
        landlord_id = join.landlord_id

        with use_landlord(landlord_id):
            landlord = Landlord.objects.get(id=landlord_id)
            org_unit = OrgUnit.objects.select_related("parent").get(
                id=join.org_unit_id
            )
            if (
                landlord.status != Landlord.Status.ACTIVE
                or org_unit.status != OrgUnit.Status.ACTIVE
            ):
                raise InvalidJoinCode

            active_owner_exists = StaffRoleAssignment.objects.filter(
                landlord_id=landlord_id,
                org_unit__kind=OrgUnit.Kind.ROOT,
                role__codename="OWNER",
                staff__status=Staff.Status.ACTIVE,
                staff__landlord__status=Landlord.Status.ACTIVE,
            ).exists()
            verified_owner_exists = StaffRoleAssignment.objects.filter(
                landlord_id=landlord_id,
                org_unit__kind=OrgUnit.Kind.ROOT,
                role__codename="OWNER",
                staff__status=Staff.Status.ACTIVE,
                staff__user__is_active=True,
                staff__user__is_phone_verified=True,
            ).exists()
            unverified_owner_exists = StaffRoleAssignment.objects.filter(
                landlord_id=landlord_id,
                org_unit__kind=OrgUnit.Kind.ROOT,
                role__codename="OWNER",
                staff__status=Staff.Status.ACTIVE,
                staff__user__is_active=True,
                staff__user__is_phone_verified=False,
            ).exists()
            if (
                not active_owner_exists
                or not verified_owner_exists
                or unverified_owner_exists
            ):
                raise InvalidJoinCode

            existing = TenantProfile.objects.filter(
                landlord_id=landlord_id,
                user=user,
                status__in=[
                    TenantProfile.Status.PENDING,
                    TenantProfile.Status.ACTIVE,
                ],
            ).first()
            if existing is not None:
                return existing

            previously_evicted = TenantProfile.objects.filter(
                landlord_id=landlord_id,
                user=user,
                status=TenantProfile.Status.EVICTED,
            ).exists()
            approval_required = effective_approval_required(
                landlord,
                org_unit,
            )
            initial_status = (
                TenantProfile.Status.PENDING
                if previously_evicted or approval_required
                else TenantProfile.Status.ACTIVE
            )

            try:
                with transaction.atomic():
                    now = timezone.now()
                    claim = JoinCode.all_objects.filter(
                        id=join.id,
                        is_active=True,
                        revoked_at__isnull=True,
                    ).filter(
                        Q(expires_at__isnull=True)
                        | Q(expires_at__gt=now)
                    ).filter(
                        Q(max_uses__isnull=True)
                        | Q(uses__lt=F("max_uses"))
                    ).update(uses=F("uses") + 1)
                    if claim != 1:
                        raise InvalidJoinCode

                    profile = TenantProfile.objects.create(
                        landlord_id=landlord_id,
                        user=user,
                        org_unit=org_unit,
                        display_name=display_name,
                        status=initial_status,
                        join_code=join,
                    )
            except IntegrityError:
                existing = TenantProfile.objects.filter(
                    landlord_id=landlord_id,
                    user=user,
                    status__in=[
                        TenantProfile.Status.PENDING,
                        TenantProfile.Status.ACTIVE,
                    ],
                ).first()
                if existing is not None:
                    return existing
                raise

            TenantStatusHistory.objects.create(
                landlord_id=landlord_id,
                tenant_profile=profile,
                from_status=None,
                to_status=profile.status,
                reason="Joined through a valid join code",
            )
            write_audit(
                landlord_id=landlord_id,
                actor_user=user,
                actor_staff=None,
                action="tenant.join",
                target_type="TenantProfile",
                target_id=str(profile.id),
                before=None,
                after={"status": profile.status},
            )

            if profile.status == TenantProfile.Status.PENDING:
                approvers = list(approver_users(org_unit))
                transaction.on_commit(
                    lambda: [
                        notify(
                            "TENANT_PENDING_ALERT",
                            approver,
                            {
                                "tenant_name": display_name,
                                "landlord_id": str(landlord_id),
                            },
                        )
                        for approver in approvers
                    ]
                )
            transaction.on_commit(
                lambda: notify(
                    "TENANT_JOIN_RECEIVED",
                    user,
                    {
                        "landlord_name": landlord.name,
                        "status": profile.status.lower(),
                        "landlord_id": str(landlord_id),
                    },
                )
            )
            return profile


def effective_approval_required(landlord, org_unit):
    node = org_unit
    visited = set()
    while node is not None and node.id not in visited:
        visited.add(node.id)
        if node.require_tenant_approval is not None:
            return node.require_tenant_approval
        node = node.parent
    return landlord.require_tenant_approval


def _tenant_transition(
    profile_id,
    to_status,
    reason,
    actor_user,
    actor_staff,
    permission,
):
    if len(reason.strip()) < 10:
        raise ValueError("A reason of at least 10 characters is required")

    profile = TenantProfile.objects.select_for_update().get(id=profile_id)
    if not profile.landlord.status == "ACTIVE":
        raise ValueError("Landlord is not active")
    if not has_perm(actor_staff, permission, profile.org_unit):
        raise PermissionError("Permission denied")

    allowed = {
        TenantProfile.Status.PENDING: (
            TenantProfile.Status.ACTIVE,
            TenantProfile.Status.REJECTED,
        ),
        TenantProfile.Status.ACTIVE: (
            TenantProfile.Status.SHIFTED,
            TenantProfile.Status.EVICTED,
        ),
    }
    if to_status not in allowed.get(profile.status, ()):
        raise ValueError("Invalid tenant status transition")

    with transaction.atomic():
        from_status = profile.status
        profile.status = to_status
        profile.status_reason = reason
        if to_status == TenantProfile.Status.ACTIVE:
            profile.approved_by = actor_staff
            profile.approved_at = timezone.now()
        profile.save(update_fields=[
            "status",
            "status_reason",
            "approved_by",
            "approved_at",
        ])
        history = TenantStatusHistory.objects.create(
            landlord_id=profile.landlord_id,
            tenant_profile=profile,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            changed_by=actor_staff,
        )
        write_audit(
            landlord_id=profile.landlord_id,
            actor_user=actor_user,
            actor_staff=actor_staff,
            action=f"tenant.{to_status.lower()}",
            target_type="TenantProfile",
            target_id=str(profile.id),
            before={"status": from_status},
            after={"status": to_status, "reason": reason},
        )
    return profile, history


@transaction.atomic
def approve_tenant(profile_id, actor_user, actor_staff):
    profile, _history = _tenant_transition(
        profile_id,
        TenantProfile.Status.ACTIVE,
        "Approved by authorized staff",
        actor_user,
        actor_staff,
        "tenant.approve",
    )
    transaction.on_commit(
        lambda: notify(
            "TENANT_APPROVED",
            profile.user,
            {"landlord_name": profile.landlord.name},
        )
    )
    return profile


@transaction.atomic
def reject_tenant(profile_id, reason, actor_user, actor_staff):
    profile, _history = _tenant_transition(
        profile_id,
        TenantProfile.Status.REJECTED,
        reason,
        actor_user,
        actor_staff,
        "tenant.reject",
    )
    transaction.on_commit(
        lambda: notify(
            "TENANT_REJECTED",
            profile.user,
            {"landlord_name": profile.landlord.name},
        )
    )
    return profile


@transaction.atomic
def shift_tenant(profile_id, org_unit_id, reason, actor_user, actor_staff):
    profile = TenantProfile.objects.select_for_update().get(id=profile_id)
    target = OrgUnit.objects.select_for_update().get(id=org_unit_id)
    if target.landlord_id != profile.landlord_id:
        raise PermissionError("Cross-landlord org unit")
    if not has_perm(actor_staff, "tenant.shift", target):
        raise PermissionError("Permission denied")
    if len(reason.strip()) < 10:
        raise ValueError("A reason of at least 10 characters is required")
    if profile.status != TenantProfile.Status.ACTIVE:
        raise ValueError("Only active tenants can be shifted")

    old_org_unit_id = profile.org_unit_id
    old_status = profile.status
    profile.org_unit = target
    profile.status = TenantProfile.Status.SHIFTED
    profile.status_reason = reason
    profile.save(update_fields=[
        "org_unit",
        "status",
        "status_reason",
    ])
    history = TenantStatusHistory.objects.create(
        landlord_id=profile.landlord_id,
        tenant_profile=profile,
        from_status=old_status,
        to_status=TenantProfile.Status.SHIFTED,
        reason=reason,
        changed_by=actor_staff,
    )
    write_audit(
        landlord_id=profile.landlord_id,
        actor_user=actor_user,
        actor_staff=actor_staff,
        action="tenant.shift",
        target_type="TenantProfile",
        target_id=str(profile.id),
        before={
            "status": old_status,
            "org_unit_id": str(old_org_unit_id),
        },
        after={
            "status": TenantProfile.Status.SHIFTED,
            "org_unit_id": str(org_unit_id),
        },
    )
    transaction.on_commit(
        lambda: notify(
            "TENANT_SHIFTED",
            profile.user,
            {
                "landlord_name": profile.landlord.name,
                "org_unit_name": target.name,
            },
        )
    )
    return profile


@transaction.atomic
def evict_tenant(profile_id, reason, actor_user, actor_staff):
    profile, _history = _tenant_transition(
        profile_id,
        TenantProfile.Status.EVICTED,
        reason,
        actor_user,
        actor_staff,
        "tenant.evict",
    )
    transaction.on_commit(
        lambda: notify(
            "TENANT_EVICTED",
            profile.user,
            {"landlord_name": profile.landlord.name},
        )
    )
    return profile


def add_tenant(
    landlord_id,
    org_unit,
    user,
    display_name,
    actor_user,
    actor_staff,
):
    if not has_perm(actor_staff, "tenant.create", org_unit):
        raise PermissionError("Permission denied")
    with use_landlord(landlord_id):
        profile, created = TenantProfile.objects.get_or_create(
            landlord_id=landlord_id,
            user=user,
            defaults={
                "org_unit": org_unit,
                "display_name": display_name,
                "status": TenantProfile.Status.PENDING,
                "admitted_by": actor_staff,
            },
        )
        if not created:
            raise ValueError("A tenant profile already exists")
        TenantStatusHistory.objects.create(
            landlord_id=landlord_id,
            tenant_profile=profile,
            from_status=None,
            to_status=TenantProfile.Status.PENDING,
            reason="Created by staff",
            changed_by=actor_staff,
        )
        write_audit(
            landlord_id=landlord_id,
            actor_user=actor_user,
            actor_staff=actor_staff,
            action="tenant.create",
            target_type="TenantProfile",
            target_id=str(profile.id),
            before=None,
            after={"status": TenantProfile.Status.PENDING},
        )
        transaction.on_commit(
            lambda: notify(
                "TENANT_ADDED",
                user,
                {"landlord_name": profile.landlord.name},
            )
        )
    return profile


ALLOWED_NATIONAL_ID_TYPES = {
    "image/jpeg",
    "image/png",
    "application/pdf",
}
MAX_NATIONAL_ID_BYTES = 5 * 1024 * 1024


@transaction.atomic
def upload_national_id(profile_id, uploaded_file, actor_staff):
    profile = TenantProfile.objects.select_for_update().get(id=profile_id)
    if not has_perm(actor_staff, "tenant.view_identity", profile.org_unit):
        raise PermissionError("Permission denied")
    if uploaded_file.size is None or uploaded_file.size <= 0:
        raise ValueError("National ID file is empty")
    if uploaded_file.size > MAX_NATIONAL_ID_BYTES:
        raise ValueError("National ID file exceeds 5 MB")
    content_type = (
        getattr(uploaded_file, "content_type", None)
        or mimetypes.guess_type(uploaded_file.name)[0]
    )
    if content_type not in ALLOWED_NATIONAL_ID_TYPES:
        raise ValueError("Unsupported national ID content type")

    key = (
        f"national-ids/{profile.landlord_id}/"
        f"{profile.id}/{uuid.uuid4()}/{uploaded_file.name}"
    )
    stored_key = default_storage.save(key, uploaded_file)
    profile.national_id_key = stored_key
    profile.save(update_fields=["national_id_key"])
    write_audit(
        landlord_id=profile.landlord_id,
        actor_user=getattr(actor_staff, "user", None),
        actor_staff=actor_staff,
        action="tenant.national_id.upload",
        target_type="TenantProfile",
        target_id=str(profile.id),
        before=None,
        after={"national_id_key": stored_key},
    )
    return stored_key


def signed_national_id_url(profile_id, actor_staff):
    profile = TenantProfile.objects.get(id=profile_id)
    if not has_perm(actor_staff, "tenant.view_identity", profile.org_unit):
        raise PermissionError("Permission denied")
    if not profile.national_id_key:
        raise ValueError("No national ID is uploaded")

    storage = default_storage
    if hasattr(storage, "url"):
        url_method = getattr(storage, "url")
        if getattr(settings, "DEBUG", False):
            return url_method(profile.national_id_key)
        return url_method(profile.national_id_key, expire=300)
    raise RuntimeError("Storage does not provide signed URLs")
