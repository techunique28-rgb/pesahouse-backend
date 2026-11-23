import html
from dataclasses import dataclass


@dataclass(frozen=True)
class WhatsAppTemplate:
    name: str
    language: str
    variables: tuple[str, ...]


TEMPLATE_REGISTRY = {
    "OTP_SIGNUP": ("en", "Your PesaHouse signup code is {otp}. It expires in 5 minutes."),
    "OTP_LOGIN": ("en", "Your PesaHouse login code is {otp}. It expires in 5 minutes."),
    "OTP_RESET": ("en", "Your PesaHouse password reset code is {otp}. It expires in 5 minutes."),
    "OTP_CLAIM": ("en", "Your PesaHouse account claim code is {otp}. It expires in 5 minutes."),
    "STAFF_INVITE": ("en", "You have been invited to {landlord_name}. Use join code {code}."),
    "TENANT_ADDED": ("en", "{landlord_name} added you as a tenant."),
    "TENANT_JOIN_RECEIVED": (
        "en",
        "Your request to join {landlord_name} is {status}.",
    ),
    "TENANT_PENDING_ALERT": ("en", "Tenant {tenant_name} is waiting for approval."),
    "TENANT_APPROVED": ("en", "Your tenancy at {landlord_name} was approved."),
    "TENANT_REJECTED": ("en", "Your tenancy request at {landlord_name} was rejected."),
    "TENANT_SHIFTED": ("en", "Your tenancy at {landlord_name} has been moved to {org_unit_name}."),
    "TENANT_EVICTED": ("en", "Your tenancy at {landlord_name} has been ended."),
    "PASSWORD_CHANGED": ("en", "Your PesaHouse password was changed."),
    "JOIN_CODE_ROTATED": ("en", "The join code for {org_unit_name} is now {code}."),
}


WHATSAPP_TEMPLATE_REGISTRY = {
    "OTP_SIGNUP": WhatsAppTemplate("pesahouse_otp_signup", "en", ("otp",)),
    "OTP_LOGIN": WhatsAppTemplate("pesahouse_otp_login", "en", ("otp",)),
    "OTP_RESET": WhatsAppTemplate("pesahouse_otp_reset", "en", ("otp",)),
    "OTP_CLAIM": WhatsAppTemplate("pesahouse_otp_claim", "en", ("otp",)),
    "STAFF_INVITE": WhatsAppTemplate(
        "pesahouse_staff_invite", "en", ("landlord_name", "code")
    ),
    "TENANT_ADDED": WhatsAppTemplate("pesahouse_tenant_added", "en", ("landlord_name",)),
    "TENANT_JOIN_RECEIVED": WhatsAppTemplate(
        "pesahouse_tenant_join_received",
        "en",
        ("landlord_name", "status"),
    ),
    "TENANT_PENDING_ALERT": WhatsAppTemplate(
        "pesahouse_tenant_pending", "en", ("tenant_name",)
    ),
    "TENANT_APPROVED": WhatsAppTemplate(
        "pesahouse_tenant_approved", "en", ("landlord_name",)
    ),
    "TENANT_REJECTED": WhatsAppTemplate(
        "pesahouse_tenant_rejected", "en", ("landlord_name",)
    ),
    "TENANT_SHIFTED": WhatsAppTemplate(
        "pesahouse_tenant_shifted", "en", ("landlord_name", "org_unit_name")
    ),
    "TENANT_EVICTED": WhatsAppTemplate(
        "pesahouse_tenant_evicted", "en", ("landlord_name",)
    ),
    "PASSWORD_CHANGED": WhatsAppTemplate("pesahouse_password_changed", "en", tuple()),
    "JOIN_CODE_ROTATED": WhatsAppTemplate(
        "pesahouse_join_code_rotated", "en", ("org_unit_name", "code")
    ),
}


def render_template(purpose: str, context: dict) -> str:
    if purpose not in TEMPLATE_REGISTRY:
        raise ValueError("Unknown notification purpose")
    _language, template = TEMPLATE_REGISTRY[purpose]
    try:
        rendered = template.format(
            **{key: html.escape(str(value)) for key, value in context.items()}
        )
    except KeyError as exc:
        raise ValueError(f"Missing notification template variable: {exc.args[0]}") from exc
    if len(rendered) > 1600:
        raise ValueError("Notification template rendered beyond length limit")
    return rendered
