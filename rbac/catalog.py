PERMISSION_CATALOG = {
    "staff.view": "View staff",
    "staff.invite": "Invite staff",
    "staff.manage": "Manage staff",
    "staff.remove": "Remove staff",
    "role.manage": "Manage roles",
    "orgunit.manage": "Manage organization units",
    "joincode.manage": "Manage join codes",
    "tenant.view": "View tenants",
    "tenant.create": "Create tenant profiles",
    "tenant.approve": "Approve tenant profiles",
    "tenant.reject": "Reject tenant profiles",
    "tenant.shift": "Shift tenants",
    "tenant.evict": "Evict tenants",
    "tenant.view_identity": "View tenant identity documents",
    "landlord.settings": "Manage landlord settings",
    "audit.view": "View audit logs",
}

SYSTEM_ROLE_TEMPLATES = {
    "OWNER": {
        "name": "Owner",
        "locked": True,
        "permissions": set(PERMISSION_CATALOG),
    },
    "MANAGER": {
        "name": "Manager",
        "locked": True,
        "permissions": set(PERMISSION_CATALOG) - {
            "landlord.settings",
            "role.manage",
        },
    },
    "CLERK": {
        "name": "Clerk",
        "locked": True,
        "permissions": {
            "tenant.view",
            "tenant.create",
        },
    },
    "CARETAKER": {
        "name": "Caretaker",
        "locked": True,
        "permissions": {"tenant.view"},
    },
}
