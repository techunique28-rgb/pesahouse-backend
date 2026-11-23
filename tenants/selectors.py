from django.contrib.auth import get_user_model

from rbac.models import Staff, StaffRoleAssignment

from .models import TenantProfile


def tenant_list(*, status=None):
    queryset = TenantProfile.objects.select_related(
        "user",
        "org_unit",
        "admitted_by",
        "approved_by",
    )
    if status:
        queryset = queryset.filter(status=status)
    return queryset


def tenant_detail(profile_id):
    return TenantProfile.objects.select_related(
        "user",
        "org_unit",
        "admitted_by",
        "approved_by",
    ).get(id=profile_id)


def approver_users(org_unit):
    ancestor_ids = [
        value
        for value in org_unit.path.strip("/").split("/")
        if value
    ]
    approver_ids = StaffRoleAssignment.objects.filter(
        landlord_id=org_unit.landlord_id,
        staff__status=Staff.Status.ACTIVE,
        staff__user__is_active=True,
        staff__landlord__status="ACTIVE",
        org_unit_id__in=ancestor_ids,
        org_unit__landlord_id=org_unit.landlord_id,
        role__landlord_id__in=(None, org_unit.landlord_id),
        role__role_permissions__permission_id="tenant.approve",
    ).values_list("staff__user_id", flat=True)
    return get_user_model().objects.filter(
        is_active=True,
        id__in=approver_ids,
    ).distinct()
