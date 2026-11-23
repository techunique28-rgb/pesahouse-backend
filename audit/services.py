from django.db import transaction

from .models import AuditLog


@transaction.atomic
def write_audit(
    landlord_id,
    actor_user,
    actor_staff,
    action,
    target_type,
    target_id,
    before=None,
    after=None,
    ip=None,
    request_id="",
):
    return AuditLog.objects.create(
        landlord_id=landlord_id,
        actor_user=actor_user,
        actor_staff=actor_staff,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        before=before,
        after=after,
        ip=ip,
        request_id=request_id,
    )
