"""Client-onboarding lifecycle — the workflow behind every step from signed contract to first login.

The commercial lifecycle starts *before* a tenant exists:

  1. intake        — a pre-tenant application (company + region + user roster + documents), fillable by the
                     client over a tokenized link or by a Tellumen operator on their behalf.
  2. provision     — one operator action: create the tenant (region-pinned, entitlements + least-privilege
                     roles), create every rostered user as 'invited', file signed documents into the vault,
                     and email each user a secure activation link.
  3. activate      — each user sets their own password (never a plaintext one we chose) and enrols MFA (TOTP),
                     which is mandatory for this regulated platform. Only then does the account go 'active'.

Everything is org-scoped once a tenant exists; pre-tenant rows key off the intake. This module owns the state
machine; the router is a thin HTTP skin over it. It reuses create_tenant, the contracts vault, and the email
outbox rather than re-implementing them.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from api.security import hash_password
from api.services.rbac import write_audit
from core.config import settings
from services.governance import contracts as vault
from services.governance import totp
from services.governance.tenant_provisioning import (
    DEFAULT_ENTITLEMENTS,
    VALID_ORG_TYPES,
    TenantError,
    create_tenant,
)
from services.notifications.mailer import queue_email

ROSTER_ROLES = {"admin", "analyst", "approver", "viewer"}
VALID_REGIONS = {"EU", "US"}
INTAKE_TOKEN_TTL_DAYS = 14
ACTIVATION_TTL_HOURS = 72


class OnboardingError(ValueError):
    """A client-facing onboarding validation failure (maps to HTTP 400/409)."""


# ── token helpers ────────────────────────────────────────────────────────────
def _new_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def intake_form_url(token: str) -> str:
    return f"{settings.APP_BASE_URL.rstrip('/')}/onboarding/form/{token}"


def activation_url(token: str) -> str:
    return f"{settings.APP_BASE_URL.rstrip('/')}/activate/{token}"


# ── intake CRUD (operator side) ──────────────────────────────────────────────
def create_intake(
    session: Session,
    *,
    actor_user_id: str | None,
    actor_org_id: str | None,
    company_name: str,
    org_type: str,
    contact_email: str,
    contact_name: str | None = None,
    country: str | None = None,
    region: str = "EU",
    legal_name: str | None = None,
    lei: str | None = None,
    filing_contact_email: str | None = None,
    modules: list[str] | None = None,
    notes: str | None = None,
) -> dict:
    """Open a pre-tenant intake and mint a tokenized link the client (or an operator) fills. Status → invited."""
    company_name = (company_name or "").strip()
    if not company_name:
        raise OnboardingError("company_name is required")
    org_type = (org_type or "").strip().lower()
    if org_type not in VALID_ORG_TYPES:
        raise OnboardingError(f"org_type must be one of {sorted(VALID_ORG_TYPES)}")
    contact_email = (contact_email or "").strip().lower()
    if "@" not in contact_email:
        raise OnboardingError("a valid contact_email is required")
    region = (region or "EU").strip().upper()
    if region not in VALID_REGIONS:
        raise OnboardingError(f"region must be one of {sorted(VALID_REGIONS)}")
    country = (country or "").strip().upper()[:2] or None
    mods = modules if modules is not None else list(DEFAULT_ENTITLEMENTS.get(org_type, []))

    raw, token_hash = _new_token()
    intake_id = str(uuid.uuid4())
    session.execute(text("""
        INSERT INTO client_intake
          (intake_id, company_name, org_type, country, region, legal_name, lei, filing_contact_email,
           contact_name, contact_email, modules, status, token_hash, token_expires_at, notes, created_by, created_at)
        VALUES
          (CAST(:id AS uuid), :name, :otype, :country, :region, :legal, :lei, :fce,
           :cname, :cemail, CAST(:mods AS jsonb), 'invited', :th, :exp, :notes, :by, now())
    """), {
        "id": intake_id, "name": company_name, "otype": org_type, "country": country, "region": region,
        "legal": legal_name, "lei": lei, "fce": filing_contact_email, "cname": contact_name,
        "cemail": contact_email, "mods": json.dumps(mods),
        "th": token_hash, "exp": _now() + timedelta(days=INTAKE_TOKEN_TTL_DAYS),
        "notes": notes, "by": actor_user_id,
    })
    write_audit(session, org_id=actor_org_id, actor_user_id=actor_user_id, action="intake.created",
                target_type="client_intake", target_id=intake_id, detail={"company": company_name, "org_type": org_type})
    session.commit()
    return {"intake_id": intake_id, "status": "invited", "form_token": raw, "form_url": intake_form_url(raw)}


def _intake_row(session: Session, intake_id: str) -> dict | None:
    r = session.execute(text("SELECT * FROM client_intake WHERE intake_id = CAST(:i AS uuid)"),
                        {"i": intake_id}).mappings().first()
    return dict(r) if r else None


def _roster(session: Session, intake_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT roster_id, email, full_name, role, created_user_id
        FROM client_intake_user WHERE intake_id = CAST(:i AS uuid) ORDER BY created_at
    """), {"i": intake_id}).mappings().all()
    return [dict(r) for r in rows]


def _documents(session: Session, intake_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT document_id, kind, title, filename, content_type, size_bytes, to_vault, contract_type, uploaded_at
        FROM client_intake_document WHERE intake_id = CAST(:i AS uuid) ORDER BY uploaded_at
    """), {"i": intake_id}).mappings().all()
    return [dict(r) for r in rows]


def get_intake(session: Session, intake_id: str) -> dict | None:
    row = _intake_row(session, intake_id)
    if not row:
        return None
    row.pop("token_hash", None)
    row["roster"] = _roster(session, intake_id)
    row["documents"] = _documents(session, intake_id)
    return row


def list_intakes(session: Session) -> list[dict]:
    rows = session.execute(text("""
        SELECT i.intake_id, i.company_name, i.org_type, i.country, i.region, i.status,
               i.contact_email, i.provisioned_org_id, i.created_at, i.submitted_at, i.provisioned_at,
               (SELECT count(*) FROM client_intake_user u WHERE u.intake_id = i.intake_id) AS roster_count,
               (SELECT count(*) FROM client_intake_document d WHERE d.intake_id = i.intake_id) AS document_count
        FROM client_intake i ORDER BY i.created_at DESC
    """)).mappings().all()
    return [dict(r) for r in rows]


# ── intake fill (client side, token-authenticated) ───────────────────────────
def get_intake_by_token(session: Session, token: str) -> dict | None:
    """Resolve a self-serve form link. Returns the intake (public fields + roster) if the token is live."""
    r = session.execute(text("""
        SELECT * FROM client_intake WHERE token_hash = :th
          AND status IN ('invited','submitted','in_review')
          AND (token_expires_at IS NULL OR token_expires_at > now())
    """), {"th": _hash(token)}).mappings().first()
    if not r:
        return None
    row = dict(r)
    intake_id = str(row["intake_id"])
    row.pop("token_hash", None)
    row["roster"] = _roster(session, intake_id)
    row["documents"] = _documents(session, intake_id)
    return row


def submit_intake_form(session: Session, token: str, payload: dict) -> dict:
    """Client (or operator) fills the form: company identity, region, module selection, and the user roster.
    Replaces the roster wholesale. Status → submitted."""
    r = session.execute(text("""
        SELECT intake_id FROM client_intake WHERE token_hash = :th
          AND status IN ('invited','submitted','in_review')
          AND (token_expires_at IS NULL OR token_expires_at > now())
    """), {"th": _hash(token)}).mappings().first()
    if not r:
        raise OnboardingError("this onboarding link is invalid or has expired")
    intake_id = str(r["intake_id"])

    country = (payload.get("country") or "").strip().upper()[:2] or None
    region = (payload.get("region") or "EU").strip().upper()
    if region not in VALID_REGIONS:
        raise OnboardingError(f"region must be one of {sorted(VALID_REGIONS)}")
    roster = payload.get("roster") or []
    clean_roster = _validate_roster(roster)

    session.execute(text("""
        UPDATE client_intake SET
          company_name = COALESCE(NULLIF(:name,''), company_name),
          country = :country, region = :region,
          legal_name = :legal, lei = :lei, filing_contact_email = :fce,
          aum_eur = :aum, employees = :emp,
          modules = CAST(:mods AS jsonb),
          contact_name = COALESCE(NULLIF(:cname,''), contact_name),
          status = 'submitted', submitted_at = now()
        WHERE intake_id = CAST(:i AS uuid)
    """), {
        "name": (payload.get("company_name") or "").strip(), "country": country, "region": region,
        "legal": payload.get("legal_name"), "lei": payload.get("lei"),
        "fce": payload.get("filing_contact_email"),
        "aum": payload.get("aum_eur"), "emp": payload.get("employees"),
        "mods": json.dumps(payload.get("modules") or []),
        "cname": (payload.get("contact_name") or "").strip(), "i": intake_id,
    })
    session.execute(text("DELETE FROM client_intake_user WHERE intake_id = CAST(:i AS uuid)"), {"i": intake_id})
    for m in clean_roster:
        session.execute(text("""
            INSERT INTO client_intake_user (intake_id, email, full_name, role)
            VALUES (CAST(:i AS uuid), :email, :name, :role)
        """), {"i": intake_id, "email": m["email"], "name": m.get("full_name"), "role": m["role"]})
    session.commit()
    return get_intake(session, intake_id)


def _validate_roster(roster: list[dict]) -> list[dict]:
    clean, seen = [], set()
    for m in roster:
        email = (m.get("email") or "").strip().lower()
        if "@" not in email or email in seen:
            continue
        seen.add(email)
        role = (m.get("role") or "viewer").strip().lower()
        if role not in ROSTER_ROLES:
            role = "viewer"
        clean.append({"email": email, "full_name": (m.get("full_name") or "").strip() or None, "role": role})
    return clean


def add_intake_document(
    session: Session, intake_id: str, *, kind: str, title: str, filename: str,
    content_type: str, data: bytes, to_vault: bool = False, contract_type: str | None = None,
) -> dict:
    if not data:
        raise OnboardingError("empty file")
    if len(data) > 25 * 1024 * 1024:
        raise OnboardingError("file exceeds 25MB")
    doc_id = str(uuid.uuid4())
    session.execute(text("""
        INSERT INTO client_intake_document
          (document_id, intake_id, kind, title, filename, content_type, data, size_bytes, to_vault, contract_type)
        VALUES (CAST(:d AS uuid), CAST(:i AS uuid), :kind, :title, :fn, :ct, :data, :sz, :tv, :cty)
    """), {"d": doc_id, "i": intake_id, "kind": kind, "title": title, "fn": filename, "ct": content_type,
           "data": data, "sz": len(data), "tv": to_vault, "cty": contract_type})
    session.commit()
    return {"document_id": doc_id, "filename": filename, "size_bytes": len(data), "to_vault": to_vault}


# ── provisioning (operator side) ─────────────────────────────────────────────
def provision_from_intake(session: Session, *, actor_user_id: str | None, intake_id: str) -> dict:
    """One action: stand up the tenant, create every rostered user as 'invited', file signed documents into the
    vault, and issue each user a secure activation link. Idempotency guard: refuses an already-provisioned intake."""
    intake = _intake_row(session, intake_id)
    if not intake:
        raise OnboardingError("intake not found")
    if intake["status"] == "provisioned":
        raise OnboardingError("this intake has already been provisioned")
    if not intake["country"]:
        raise OnboardingError("country is required before provisioning — ask the client to complete the intake")
    roster = _roster(session, intake_id)
    if not roster:
        raise OnboardingError("the user roster is empty — at least one admin is required")
    if not any(m["role"] == "admin" for m in roster):
        raise OnboardingError("the roster needs at least one admin so the tenant is usable")

    modules = intake["modules"] if isinstance(intake["modules"], list) else json.loads(intake["modules"] or "[]")
    try:
        tenant = create_tenant(
            session, actor_user_id=actor_user_id, name=intake["company_name"], org_type=intake["org_type"],
            country=intake["country"], legal_name=intake["legal_name"], lei=intake["lei"],
            filing_contact_email=intake["filing_contact_email"], entitlements=modules or None,
        )  # commits internally
    except TenantError as e:
        raise OnboardingError(str(e)) from e
    org_id = tenant["org_id"]

    # region (data residency) is not part of create_tenant — stamp it now
    session.execute(text("UPDATE organizations SET region = :r WHERE org_id = CAST(:o AS uuid)"),
                    {"r": intake["region"], "o": org_id})

    # map role name → role_id for this new tenant
    role_ids = {r["name"]: str(r["role_id"]) for r in session.execute(text(
        "SELECT role_id, name FROM roles WHERE org_id = CAST(:o AS uuid)"), {"o": org_id}).mappings().all()}

    created_users = []
    for m in roster:
        user_id = str(uuid.uuid4())
        session.execute(text("""
            INSERT INTO users (user_id, org_id, email, role, full_name, hashed_password, status, created_at)
            VALUES (CAST(:u AS uuid), CAST(:o AS uuid), :email, :role, :name, NULL, 'invited', now())
        """), {"u": user_id, "o": org_id, "email": m["email"], "role": m["role"], "name": m["full_name"]})
        rid = role_ids.get(m["role"]) or role_ids.get("viewer")
        if rid:
            session.execute(text("""
                INSERT INTO user_roles (user_id, role_id, granted_by)
                VALUES (CAST(:u AS uuid), CAST(:r AS uuid), :by) ON CONFLICT DO NOTHING
            """), {"u": user_id, "r": rid, "by": actor_user_id})
        session.execute(text("UPDATE client_intake_user SET created_user_id = CAST(:u AS uuid) WHERE roster_id = CAST(:rid AS uuid)"),
                        {"u": user_id, "rid": str(m["roster_id"])})
        link = _issue_activation(session, org_id=org_id, user_id=user_id, email=m["email"], full_name=m["full_name"],
                                 company=intake["company_name"])
        created_users.append({"email": m["email"], "role": m["role"], "activation_url": link})

    write_audit(session, org_id=org_id, actor_user_id=actor_user_id, action="tenant.provisioned_from_intake",
                target_type="client_intake", target_id=intake_id,
                detail={"users": len(created_users), "region": intake["region"]})
    session.execute(text("""
        UPDATE client_intake SET status = 'provisioned', provisioned_org_id = CAST(:o AS uuid),
          provisioned_at = now(), token_hash = NULL WHERE intake_id = CAST(:i AS uuid)
    """), {"o": org_id, "i": intake_id})
    session.commit()

    # file flagged documents into the tenant's contracts vault (add_contract commits internally)
    filed = _file_documents_to_vault(session, org_id=org_id, actor_user_id=actor_user_id, intake_id=intake_id)

    return {"org_id": org_id, "org_name": tenant["name"], "region": intake["region"],
            "users": created_users, "contracts_filed": filed}


def _issue_activation(session: Session, *, org_id: str, user_id: str, email: str, full_name: str | None, company: str) -> str:
    raw, token_hash = _new_token()
    activation_id = str(uuid.uuid4())
    session.execute(text("""
        INSERT INTO user_activation (activation_id, user_id, org_id, token_hash, status, expires_at)
        VALUES (CAST(:a AS uuid), CAST(:u AS uuid), CAST(:o AS uuid), :th, 'pending', :exp)
    """), {"a": activation_id, "u": user_id, "o": org_id, "th": token_hash,
           "exp": _now() + timedelta(hours=ACTIVATION_TTL_HOURS)})
    link = activation_url(raw)
    greeting = (full_name or email).split("@")[0]
    queue_email(
        session, org_id=org_id, to_email=email,
        subject=f"Activate your {company} account on Tellumen",
        html=(f"<p>Hi {greeting},</p><p>Your {company} account on Tellumen is ready. "
              f"Set your password and turn on two-factor authentication to get started:</p>"
              f"<p><a href='{link}'>Activate your account</a></p>"
              f"<p>This link expires in {ACTIVATION_TTL_HOURS} hours.</p>"),
        text_body=f"Activate your {company} account on Tellumen: {link} (expires in {ACTIVATION_TTL_HOURS}h)",
        kind="onboarding_activation", ref_type="user_activation", ref_id=activation_id,
    )
    return link


def _file_documents_to_vault(session: Session, *, org_id: str, actor_user_id: str | None, intake_id: str) -> int:
    docs = session.execute(text("""
        SELECT document_id, title, filename, content_type, contract_type, data
        FROM client_intake_document WHERE intake_id = CAST(:i AS uuid) AND to_vault = true
    """), {"i": intake_id}).mappings().all()
    filed = 0
    for d in docs:
        vault.add_contract(
            session, org_id, actor_user_id,
            title=d["title"] or d["filename"] or "Signed contract",
            filename=d["filename"] or "contract.pdf",
            content_type=d["content_type"] or "application/octet-stream",
            data=bytes(d["data"]),
            contract_type=(d["contract_type"] or "other"),
            status="active",
        )  # commits internally
        filed += 1
    return filed


# ── activation (user side, token-authenticated) ──────────────────────────────
def _activation_row(session: Session, token: str) -> dict | None:
    r = session.execute(text("""
        SELECT a.activation_id, a.user_id, a.org_id, a.status, a.expires_at,
               u.email, u.full_name, u.mfa_enrolled_at, u.hashed_password, o.name AS org_name
        FROM user_activation a JOIN users u ON u.user_id = a.user_id
        JOIN organizations o ON o.org_id = a.org_id
        WHERE a.token_hash = :th
    """), {"th": _hash(token)}).mappings().first()
    return dict(r) if r else None


def get_activation(session: Session, token: str) -> dict | None:
    """Validate an activation link and report where the user is in the flow (password set? MFA enrolled?)."""
    a = _activation_row(session, token)
    if not a or a["status"] != "pending" or a["expires_at"] <= _now():
        return None
    return {
        "email": a["email"], "full_name": a["full_name"], "org_name": a["org_name"],
        "password_set": bool(a["hashed_password"]),
        "mfa_enrolled": bool(a["mfa_enrolled_at"]),
    }


def set_activation_password(session: Session, token: str, password: str) -> dict:
    a = _activation_row(session, token)
    if not a or a["status"] != "pending" or a["expires_at"] <= _now():
        raise OnboardingError("this activation link is invalid or has expired")
    if not password or len(password) < 10:
        raise OnboardingError("password must be at least 10 characters")
    session.execute(text("UPDATE users SET hashed_password = :h, status = 'active' WHERE user_id = CAST(:u AS uuid)"),
                    {"h": hash_password(password), "u": str(a["user_id"])})
    write_audit(session, org_id=str(a["org_id"]), actor_user_id=str(a["user_id"]), action="account.password_set",
                target_type="user", target_id=str(a["user_id"]))
    session.commit()
    return {"password_set": True, "mfa_required": True}


def begin_mfa_enrollment(session: Session, token: str) -> dict:
    """Generate (or reuse) a TOTP secret for the activating user and return the provisioning URI + secret."""
    a = _activation_row(session, token)
    if not a or a["status"] != "pending" or a["expires_at"] <= _now():
        raise OnboardingError("this activation link is invalid or has expired")
    if not a["hashed_password"]:
        raise OnboardingError("set your password first")
    secret = totp.generate_secret()
    session.execute(text("UPDATE users SET mfa_secret = :s WHERE user_id = CAST(:u AS uuid)"),
                    {"s": secret, "u": str(a["user_id"])})
    session.commit()
    uri = totp.provisioning_uri(secret, a["email"])
    return {"secret": secret, "otpauth_uri": uri, "email": a["email"], "qr_data_uri": _qr_data_uri(uri)}


def _qr_data_uri(text_value: str) -> str | None:
    """Render an otpauth URI as an SVG-QR data URI (pure-Python, no imaging lib needed). Best-effort — the
    activation UI falls back to the manual-entry key if this is unavailable."""
    try:
        import base64
        import io

        import qrcode
        import qrcode.image.svg

        img = qrcode.make(text_value, image_factory=qrcode.image.svg.SvgPathImage)
        buf = io.BytesIO()
        img.save(buf)
        return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:  # noqa: BLE001 — QR is a convenience; manual-entry key always works
        return None


def confirm_mfa_enrollment(session: Session, token: str, code: str) -> dict:
    """Verify the first TOTP code, enrol MFA, and consume the activation token. Activation is now complete."""
    a = _activation_row(session, token)
    if not a or a["status"] != "pending" or a["expires_at"] <= _now():
        raise OnboardingError("this activation link is invalid or has expired")
    secret = session.execute(text("SELECT mfa_secret FROM users WHERE user_id = CAST(:u AS uuid)"),
                             {"u": str(a["user_id"])}).scalar()
    if not secret:
        raise OnboardingError("start MFA enrolment first")
    if not totp.verify(secret, code):
        raise OnboardingError("that code didn't match — check your authenticator app and try again")
    session.execute(text("UPDATE users SET mfa_enrolled_at = now() WHERE user_id = CAST(:u AS uuid)"),
                    {"u": str(a["user_id"])})
    session.execute(text("UPDATE user_activation SET status = 'used', used_at = now() WHERE activation_id = CAST(:a AS uuid)"),
                    {"a": str(a["activation_id"])})
    write_audit(session, org_id=str(a["org_id"]), actor_user_id=str(a["user_id"]), action="account.mfa_enrolled",
                target_type="user", target_id=str(a["user_id"]))
    session.commit()
    return {"activated": True, "email": a["email"]}


def resend_activation(session: Session, *, intake_id: str, actor_user_id: str | None) -> dict:
    """Re-issue activation links for every rostered user that hasn't finished activating."""
    intake = _intake_row(session, intake_id)
    if not intake or intake["status"] != "provisioned":
        raise OnboardingError("intake is not provisioned")
    org_id = str(intake["provisioned_org_id"])
    pending = session.execute(text("""
        SELECT u.user_id, u.email, u.full_name FROM users u
        WHERE u.org_id = CAST(:o AS uuid) AND u.status = 'invited'
    """), {"o": org_id}).mappings().all()
    n = 0
    for u in pending:
        session.execute(text("UPDATE user_activation SET status='expired' WHERE user_id = CAST(:u AS uuid) AND status='pending'"),
                        {"u": str(u["user_id"])})
        _issue_activation(session, org_id=org_id, user_id=str(u["user_id"]), email=u["email"],
                          full_name=u["full_name"], company=intake["company_name"])
        n += 1
    session.commit()
    return {"resent": n}
