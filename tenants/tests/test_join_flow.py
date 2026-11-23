from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.core.cache import cache
from django.db import OperationalError, close_old_connections
from django.test import TransactionTestCase

from accounts.models import User
from core.tenant_context import use_landlord
from landlords.models import JoinCode, Landlord, OrgUnit
from rbac.models import (
    Permission,
    Role,
    RolePermission,
    Staff,
    StaffRoleAssignment,
)
from tenants.models import TenantProfile
from tenants.services import InvalidJoinCode, join_with_code


class JoinFlowTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        cache.clear()
        self.notify_patcher = patch("tenants.services.notify")
        self.notify = self.notify_patcher.start()
        self.addCleanup(self.notify_patcher.stop)

        self.landlord = Landlord.objects.create(
            name="Lake View",
            require_tenant_approval=False,
        )
        self.owner_user = User.objects.create_user(
            "+256700000021",
            "StrongPass!123",
            full_name="Owner",
            is_phone_verified=True,
        )
        self.approver_user = User.objects.create_user(
            "+256700000022",
            "StrongPass!123",
            full_name="Approver",
            is_phone_verified=True,
        )
        self.unverified_owner_user = User.objects.create_user(
            "+256700000023",
            "StrongPass!123",
            full_name="Unverified Owner",
            is_phone_verified=False,
        )

        with use_landlord(self.landlord.id):
            self.root = OrgUnit.objects.create(
                landlord=self.landlord,
                parent=None,
                path="/root/",
                depth=0,
                kind=OrgUnit.Kind.ROOT,
                name=self.landlord.name,
            )
            self.root.path = f"/{self.root.id}/"
            self.root.save(update_fields=["path"])
            self.node = OrgUnit.objects.create(
                landlord=self.landlord,
                parent=self.root,
                path=f"{self.root.path}node/",
                depth=1,
                kind=OrgUnit.Kind.BRANCH,
                name="Node",
            )
            self.node.path = f"{self.root.path}{self.node.id}/"
            self.node.save(update_fields=["path"])

            self.owner_staff = Staff.objects.create(
                landlord=self.landlord,
                user=self.owner_user,
                status=Staff.Status.ACTIVE,
            )
            self.unverified_owner_staff = Staff.objects.create(
                landlord=self.landlord,
                user=self.unverified_owner_user,
                status=Staff.Status.ACTIVE,
            )
            self.approver_staff = Staff.objects.create(
                landlord=self.landlord,
                user=self.approver_user,
                status=Staff.Status.ACTIVE,
            )
            self.owner_role = Role.objects.create(
                landlord=self.landlord,
                codename="OWNER",
                name="Owner",
            )
            self.approver_role = Role.objects.create(
                landlord=self.landlord,
                codename="APPROVER",
                name="Approver",
            )
            permission = Permission.objects.create(
                code="tenant.approve",
                module="tenant",
                description="Approve tenants",
            )
            RolePermission.objects.create(
                role=self.approver_role,
                permission=permission,
            )
            StaffRoleAssignment.objects.create(
                landlord=self.landlord,
                staff=self.owner_staff,
                role=self.owner_role,
                org_unit=self.root,
                granted_by=self.owner_staff,
            )
            StaffRoleAssignment.objects.create(
                landlord=self.landlord,
                staff=self.approver_staff,
                role=self.approver_role,
                org_unit=self.root,
                granted_by=self.owner_staff,
            )
            self.join_code = JoinCode.objects.create(
                landlord=self.landlord,
                org_unit=self.node,
                code="ABCD2345",
                is_active=True,
                max_uses=5,
            )

    def make_tenant(self, phone):
        return User.objects.create_user(
            phone,
            "StrongPass!123",
            full_name="Tenant",
            is_phone_verified=True,
        )

    def set_code_limit(self, maximum):
        with use_landlord(self.landlord.id):
            self.join_code.max_uses = maximum
            self.join_code.uses = 0
            self.join_code.save(update_fields=["max_uses", "uses"])

    def test_max_uses_cannot_be_exceeded_by_concurrent_joins(self):
        self.set_code_limit(1)
        barrier = Barrier(2)
        users = [
            self.make_tenant("+256700000024"),
            self.make_tenant("+256700000025"),
        ]

        def join(user):
            close_old_connections()
            barrier.wait()
            try:
                try:
                    return join_with_code(user, "ABCD2345", " Tenant ")
                except InvalidJoinCode:
                    return None
                except OperationalError:
                    return None
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(join, users))

        with use_landlord(self.landlord.id):
            self.join_code.refresh_from_db()
            self.assertLessEqual(self.join_code.uses, 1)
            self.assertEqual(
                TenantProfile.objects.filter(
                    join_code=self.join_code,
                ).count(),
                1,
            )
        self.assertEqual(sum(result is not None for result in results), 1)

    def test_repeat_join_returns_same_profile_without_consuming_use(self):
        self.set_code_limit(1)
        tenant = self.make_tenant("+256700000026")
        first = join_with_code(tenant, "ABCD2345", "  Tenant  Name ")
        second = join_with_code(tenant, "ABCD2345", "Updated Name")

        with use_landlord(self.landlord.id):
            self.join_code.refresh_from_db()
        self.assertEqual(first.id, second.id)
        self.assertEqual(self.join_code.uses, 1)
        self.assertEqual(second.display_name, "Tenant Name")

    def test_simultaneous_repeat_joins_return_same_profile(self):
        self.set_code_limit(1)
        tenant = self.make_tenant("+256700000031")
        barrier = Barrier(2)

        def join():
            close_old_connections()
            barrier.wait()
            try:
                return join_with_code(tenant, "ABCD2345", "Tenant")
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _index: join(), range(2)))

        self.assertEqual(results[0].id, results[1].id)
        with use_landlord(self.landlord.id):
            self.join_code.refresh_from_db()
        self.assertEqual(self.join_code.uses, 1)

    def test_unverified_owner_blocks_join_code(self):
        with use_landlord(self.landlord.id):
            StaffRoleAssignment.objects.create(
                landlord=self.landlord,
                staff=self.unverified_owner_staff,
                role=self.owner_role,
                org_unit=self.root,
                granted_by=self.owner_staff,
            )
        tenant = self.make_tenant("+256700000027")
        with self.assertRaises(InvalidJoinCode):
            join_with_code(tenant, "ABCD2345", "Tenant")

    def test_pending_alert_goes_to_approver_and_tenant_gets_receipt(self):
        self.landlord.require_tenant_approval = True
        self.landlord.save(update_fields=["require_tenant_approval"])
        tenant = self.make_tenant("+256700000028")

        join_with_code(tenant, "ABCD2345", "Tenant")

        pending_recipients = [
            call.args[1]
            for call in self.notify.call_args_list
            if call.args[0] == "TENANT_PENDING_ALERT"
        ]
        self.assertEqual(
            [user.id for user in pending_recipients],
            [self.approver_user.id],
        )
        self.assertNotIn(
            tenant.id,
            [user.id for user in pending_recipients],
        )
        self.assertTrue(
            any(
                call.args[0] == "TENANT_JOIN_RECEIVED"
                and call.args[1].id == tenant.id
                for call in self.notify.call_args_list
            )
        )

    def test_evicted_tenant_always_joins_pending(self):
        tenant = self.make_tenant("+256700000029")
        with use_landlord(self.landlord.id):
            TenantProfile.objects.create(
                landlord=self.landlord,
                user=tenant,
                org_unit=self.node,
                display_name="Tenant",
                status=TenantProfile.Status.EVICTED,
                status_reason="Prior eviction recorded",
            )

        profile = join_with_code(tenant, "ABCD2345", "Tenant")
        self.assertEqual(profile.status, TenantProfile.Status.PENDING)

    def test_archived_node_blocks_join(self):
        with use_landlord(self.landlord.id):
            self.node.status = OrgUnit.Status.ARCHIVED
            self.node.save(update_fields=["status"])
        tenant = self.make_tenant("+256700000030")

        with self.assertRaises(InvalidJoinCode):
            join_with_code(tenant, "ABCD2345", "Tenant")
