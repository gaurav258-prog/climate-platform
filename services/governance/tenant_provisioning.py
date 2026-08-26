"""Tenant provisioning — create a new client org from zero, the way onboarding starts.

A new client is a new org (tenant): its identity, its entitled offerings, the default RBAC role matrix, and a
first admin who can then invite the rest of their people. Until now this only happened via a seed script; this
service is the reusable path the platform-admin onboarding flow (and the seed) both call, so a real tenant and a
demo tenant are assembled identically. Every step is audited.

HYBRID onboarding: Tellumen (platform) creates the tenant + its identity + the first admin here; the client then
completes their own book upload and invites their own users through the normal admin surfaces.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

# Canonical default role → permission matrix for a NEW tenant (single source of truth, shared with the seed).
# contracts.view / contracts.manage are included so a tenant gets contract access the moment those permissions
# exist in the catalog; a role_permissions insert for a not-yet-defined code simply grants nothing (no error).
DEFAULT_ROLE_PERMS: dict[str, list[str]] = {
    "admin": [
        "modules.view", "reports.view", "reports.publish", "pricing.view", "pricing.approve",
        "admin.users.manage", "admin.roles.manage", "admin.audit.view", "admin.approval_policy.manage",
        "approvals.create", "approvals.view", "approvals.decide", "portal.use",
        "contracts.view", "contracts.manage",
    ],
    "analyst":  ["modules.view", "reports.view", "pricing.view", "approvals.create", "portal.use"],
    "approver": ["modules.view", "reports.view", "pricing.view", "reports.publish", "pricing.approve",
                 "approvals.view", "approvals.decide", "submissions.release", "portal.use", "contracts.view"],
    "viewer":   ["modules.view", "reports.view", "pricing.view", "portal.use"],
}

VALID_ORG_TYPES = {"bank", "insurer", "asset_manager", "reit", "manufacturer"}

# Sensible default entitlements per sector (the offerings a tenant of this type gets out of the box). Callers
# may override with an explicit list. Every tenant gets 'trust' (the reporting/governance trust layer).
DEFAULT_ENTITLEMENTS: dict[str, list[str]] = {
    "bank":          ["physical-risk", "reporting", "trust"],
    "insurer":       ["underwriting", "parametric", "trust"],
    "asset_manager": ["portfolio-var", "securities", "trust"],
    "reit":          ["portfolio-risk", "trust"],
    "manufacturer":  ["supply-chain", "reporting", "trust"],
}


class TenantError(ValueError):
    """Provisioning was rejected (bad input, duplicate name/email)."""


def create_tenant(session: Session, *, actor_user_id: str | None, name: str, org_type: str,
                  country: str | None = None, legal_name: str | None = None, lei: str | None = None,
                  filing_contact_email: str | None = None, entitlements: list[str] | None = None,
                  admin_email: str | None = None, admin_full_name: str | None = None,
                  admin_password: str | None = None) -> dict:
    """Create a client tenant: org row → entitlements → default roles + permission matrix → optional first admin.
    Idempotent-ish: refuses a duplicate org name or admin email rather than creating a shadow. Returns the new
    org_id, the offerings granted, the roles created, and (if requested) the first admin's login."""
    from api.security import hash_password
    from api.services.rbac import write_audit

    name = (name or "").strip()
    country = (country or "").strip().upper() or None
    if not name:
        raise TenantError("a tenant needs a name")
    if not country:
        raise TenantError("country (ISO-2) is required")
    if org_type not in VALID_ORG_TYPES:
        raise TenantError(f"org_type must be one of {sorted(VALID_ORG_TYPES)}")
    if session.execute(text("SELECT 1 FROM organizations WHERE lower(name) = lower(:n)"), {"n": name}).first():
        raise TenantError(f"a tenant named '{name}' already exists")

    offerings = entitlements if entitlements is not None else DEFAULT_ENTITLEMENTS.get(org_type, ["trust"])

    # 1) the org (identity stamped where supplied — the rest fills in via the GLEIF identity step)
    org_id = str(uuid.uuid4())
    session.execute(text("""
        INSERT INTO organizations (org_id, name, type, country, legal_name, lei, filing_contact_email,
                                   created_at, updated_at)
        VALUES (CAST(:o AS uuid), :n, :t, :c, :ln, :lei, :fce, now(), now())
    """), {"o": org_id, "n": name, "t": org_type, "c": country, "ln": legal_name, "lei": lei,
           "fce": filing_contact_email})

    # 2) entitlements
    for off in offerings:
        session.execute(text("""
            INSERT INTO org_entitlements (org_id, offering_id, enabled) VALUES (CAST(:o AS uuid), :off, true)
            ON CONFLICT (org_id, offering_id) DO UPDATE SET enabled = true
        """), {"o": org_id, "off": off})

    # 3) roles + permission matrix (per tenant)
    for role_name, perms in DEFAULT_ROLE_PERMS.items():
        rid = session.execute(text("""
            INSERT INTO roles (org_id, name, description, is_system) VALUES (CAST(:o AS uuid), :n, :d, true)
            RETURNING role_id
        """), {"o": org_id, "n": role_name, "d": f"{role_name} role"}).scalar()
        for code in perms:
            session.execute(text("""
                INSERT INTO role_permissions (role_id, permission_id)
                SELECT :r, permission_id FROM permissions WHERE code = :c
                ON CONFLICT DO NOTHING
            """), {"r": rid, "c": code})

    # 4) optional first admin (hybrid: the platform seeds one login; the client invites the rest)
    admin = None
    if admin_email:
        admin_email = admin_email.strip().lower()
        if session.execute(text("SELECT 1 FROM users WHERE lower(email) = :e"), {"e": admin_email}).first():
            raise TenantError(f"a user with email '{admin_email}' already exists")
        if not admin_password:
            raise TenantError("a first-admin password is required when admin_email is given")
        uid = session.execute(text("""
            INSERT INTO users (user_id, org_id, email, role, full_name, hashed_password, status, created_at)
            VALUES (gen_random_uuid(), CAST(:o AS uuid), :e, 'admin', :fn, :hp, 'active', now())
            RETURNING user_id
        """), {"o": org_id, "e": admin_email, "fn": admin_full_name or admin_email, "hp": hash_password(admin_password)}).scalar()
        arid = session.execute(text("SELECT role_id FROM roles WHERE org_id = CAST(:o AS uuid) AND name = 'admin'"),
                               {"o": org_id}).scalar()
        session.execute(text("INSERT INTO user_roles (user_id, role_id) VALUES (:u, :r) ON CONFLICT DO NOTHING"),
                        {"u": uid, "r": arid})
        admin = {"user_id": str(uid), "email": admin_email}

    write_audit(session, org_id=org_id, actor_user_id=actor_user_id, action="tenant.created",
                target_type="organization", target_id=org_id,
                detail=f"Provisioned tenant '{name}' ({org_type}) · offerings {offerings}"
                       + (f" · admin {admin_email}" if admin else " · no admin seeded"))
    session.commit()
    return {"org_id": org_id, "name": name, "type": org_type, "entitlements": offerings,
            "roles": list(DEFAULT_ROLE_PERMS.keys()), "admin": admin}
