from rest_framework.permissions import BasePermission

from rbac.services import has_perm


class HasOrgPermission(BasePermission):
    permission_code = ""

    def __init__(self, permission_code: str):
        self.permission_code = permission_code

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        org_unit = getattr(view, "target_org_unit", None)
        if callable(org_unit):
            org_unit = org_unit(request)
        if org_unit is None:
            org_unit = getattr(request, "org_unit", None)
        if org_unit is None:
            return False
        return has_perm(
            getattr(request, "staff", None),
            self.permission_code,
            org_unit,
        )

    def has_object_permission(self, request, view, obj):
        org_unit = getattr(obj, "org_unit", None)
        if org_unit is None:
            org_unit = getattr(obj, "parent", None)
        if org_unit is None:
            return False
        return has_perm(
            getattr(request, "staff", None),
            self.permission_code,
            org_unit,
        )


class IsOwnTenantProfile(BasePermission):
    def has_object_permission(self, request, view, obj):
        return (
            request.user
            and request.user.is_authenticated
            and obj.user_id == request.user.id
        )
