from django.core.cache import cache
from django.test import TestCase

from accounts.models import User
from landlords.models import Landlord, OrgUnit
from rbac.models import (
    Permission,
    Role,
    RolePermission,
    Staff,
    StaffRoleAssignment,
)
from rbac.services import assign_role, bump_rbac_version, has_perm, revoke_role
from tenants.models import TenantProfile


class HasPermTests(TestCase):
    def setUp(self):
        cache.clear()
        self.landlord = Landlord.objects.create(name="A")
        self.other_landlord = Landlord.objects.create(name="B")
        self.root = OrgUnit.objects.create(
            landlord=self.landlord,
            parent=None,
            path=f"/{None}/",
            depth=0,
            kind="ROOT",
            name="A Root",
        )
        self.root.path = f"/{self.root.id}/"
        self.root.save(update_fields=["path"])
        self.division = OrgUnit.objects.create(
            landlord=self.landlord,
            parent=self.root,
            path=f"{self.root.path}{self.root.id}x/",
            depth=1,
            kind="DIVISION",
            name="Division",
        )
        self.division.path = f"{self.root.path}{self.division.id}/"
        self.division.save(update_fields=["path"])
        self.branch = OrgUnit.objects.create(
            landlord=self.landlord,
            parent=self.division,
            path=f"{self.division.path}{None}/",
            depth=2,
            kind="BRANCH",
            name="Branch",
        )
        self.branch.path = f"{self.division.path}{self.branch.id}/"
        self.branch.save(update_fields=["path"])
        self.sibling = OrgUnit.objects.create(
            landlord=self.landlord,
            parent=self.root,
            path=f"{self.root.path}{None}/",
            depth=1,
            kind="DIVISION",
            name="Sibling",
        )
        self.sibling.path = f"{self.root.path}{self.sibling.id}/"
        self.sibling.save(update_fields=["path"])
        self.other_root = OrgUnit.objects.create(
            landlord=self.other_landlord,
            parent=None,
            path=f"/{None}/",
            depth=0,
            kind="ROOT",
            name="B Root",
        )
        self.other_root.path = f"/{self.other_root.id}/"
        self.other_root.save(update_fields=["path"])

        self.user = User.objects.create_user(
            phone_e164="+256700000010",
            password="StrongPass!123",
            full_name="Staff",
        )
        self.staff = Staff.objects.create(
            landlord=self.landlord,
            user=self.user,
            status=Staff.Status.ACTIVE,
        )
        self.permission = Permission.objects.create(
            code="tenant.view",
            module="tenant",
            description="View tenants",
        )
        self.role = Role.objects.create(
            landlord=self.landlord,
            codename="TEST_ROLE",
            name="Test Role",
        )
        RolePermission.objects.create(
            role=self.role,
            permission=self.permission,
        )
        bump_rbac_version(self.landlord.id)

    def test_revoked_assignment_stops_working_immediately(self):
        assignment = assign_role(
            staff=self.staff,
            role=self.role,
            org_unit=self.root,
        )
        bump_rbac_version(self.landlord.id)
        self.assertTrue(has_perm(self.staff, "tenant.view", self.branch))
        revoke_role(assignment=assignment)
        bump_rbac_version(self.landlord.id)
        self.assertFalse(has_perm(self.staff, "tenant.view", self.branch))

    def test_moved_node_changes_access(self):
        assignment = assign_role(
            staff=self.staff,
            role=self.role,
            org_unit=self.root,
        )
        bump_rbac_version(self.landlord.id)
        self.assertTrue(has_perm(self.staff, "tenant.view", self.branch))
        old_path = self.branch.path
        self.branch.path = f"{self.sibling.path}{self.branch.id}/"
        self.branch.save(update_fields=["path"])
        bump_rbac_version(self.landlord.id)
        self.assertFalse(has_perm(self.staff, "tenant.view", self.branch))
        self.branch.path = old_path
        self.branch.save(update_fields=["path"])

    def test_suspended_staff_is_denied(self):
        assign_role(
            staff=self.staff,
            role=self.role,
            org_unit=self.root,
        )
        bump_rbac_version(self.landlord.id)
        self.staff.status = Staff.Status.SUSPENDED
        self.staff.status_reason = "Temporary suspension"
        self.staff.save(update_fields=["status", "status_reason"])
        bump_rbac_version(self.landlord.id)
        self.assertFalse(has_perm(self.staff, "tenant.view", self.branch))

    def test_cross_landlord_node_is_denied(self):
        assign_role(
            staff=self.staff,
            role=self.role,
            org_unit=self.root,
        )
        bump_rbac_version(self.landlord.id)
        self.assertFalse(has_perm(self.staff, "tenant.view", self.other_root))

    def test_parent_inherits_children_but_not_siblings_or_ancestors(self):
        assign_role(
            staff=self.staff,
            role=self.role,
            org_unit=self.root,
        )
        bump_rbac_version(self.landlord.id)
        self.assertTrue(has_perm(self.staff, "tenant.view", self.root))
        self.assertTrue(has_perm(self.staff, "tenant.view", self.branch))
        self.assertTrue(has_perm(self.staff, "tenant.view", self.sibling))

        assignment = StaffRoleAssignment.objects.filter(
            staff=self.staff,
            role=self.role,
            org_unit=self.root,
        ).first()
        assignment.org_unit = self.branch
        assignment.save(update_fields=["org_unit"])
        bump_rbac_version(self.landlord.id)
        self.assertTrue(has_perm(self.staff, "tenant.view", self.branch))
        self.assertFalse(has_perm(self.staff, "tenant.view", self.root))
        self.assertFalse(has_perm(self.staff, "tenant.view", self.sibling))

    def test_has_perm_uses_one_permission_query(self):
        assign_role(
            staff=self.staff,
            role=self.role,
            org_unit=self.root,
        )
        bump_rbac_version(self.landlord.id)
        cache.clear()
        with self.assertNumQueries(1):
            result = has_perm(
                self.staff,
                "tenant.view",
                self.branch,
            )
        self.assertTrue(result)
