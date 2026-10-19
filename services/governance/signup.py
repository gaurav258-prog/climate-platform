"""Self-serve signup — a public trial funnel that provisions a tenant + first admin instantly.

The product-led-growth path alongside sales-assisted onboarding: a prospect creates their own workspace, lands
as its admin on a 14-day trial, and can invite their team up to the trial seat limit. Reuses create_tenant so a
self-serve tenant is identical to a provisioned one — it just starts on the trial plan (optionally a sandbox).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.errors import UserError
from services.governance import billing
from services.governance.tenant_provisioning import VALID_ORG_TYPES, create_tenant

TRIAL_DAYS = 14
MIN_PASSWORD = 10


class SignupError(UserError):
    """A sign-up refusal in customer words: a catalogue code with its values (core/errors.py). Provisioning's own
    refusals (a name or an e-mail already taken) arrive as tenant_provisioning.TenantError and pass through."""


def self_serve_signup(session: Session, *, company_name: str, org_type: str, country: str,
                      admin_email: str, admin_full_name: str, password: str, sandbox: bool = False) -> dict:
    company_name = (company_name or "").strip()
    org_type = (org_type or "").strip().lower()
    admin_email = (admin_email or "").strip().lower()
    if not company_name:
        raise SignupError("admin.tenant.no_name")
    if org_type not in VALID_ORG_TYPES:
        raise SignupError("admin.tenant.bad_sector")
    if "@" not in admin_email:
        raise SignupError("platform.signup.bad_email")
    if not password or len(password) < MIN_PASSWORD:
        raise SignupError("platform.signup.password_short", min=MIN_PASSWORD)
    if not (country or "").strip():
        raise SignupError("admin.tenant.no_country")

    tenant = create_tenant(session, actor_user_id=None, name=company_name, org_type=org_type,
                           country=country, admin_email=admin_email, admin_full_name=admin_full_name,
                           admin_password=password)   # commits internally; its refusals (TenantError) pass through

    org_id = tenant["org_id"]
    session.execute(text("""
        UPDATE organizations SET plan = 'trial', trial_ends_at = :ends, environment = :env
        WHERE org_id = CAST(:o AS uuid)
    """), {"ends": datetime.now(timezone.utc) + timedelta(days=TRIAL_DAYS),
           "env": "sandbox" if sandbox else "production", "o": org_id})
    billing.ensure_subscription(session, org_id, plan="trial")
    session.commit()
    return {"org_id": org_id, "email": admin_email,
            "admin_user_id": tenant["admin"]["user_id"] if tenant.get("admin") else None}
