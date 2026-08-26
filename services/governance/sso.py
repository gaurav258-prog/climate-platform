"""Enterprise SSO — OIDC single sign-on + JIT provisioning, per tenant.

A tenant connects its own identity provider (Okta / Entra ID) over OIDC; its users sign in there and are
provisioned into Tellumen on first login (JIT) or ahead of time via SCIM (see scim.py). This module owns:
  • the per-tenant SSO config (issuer / client / JIT policy / SCIM token)
  • the OIDC login round-trip (authorize redirect → code exchange → ID-token validation → our session JWT)
  • ID-token validation, factored out as a pure function so it is unit-testable against a mock JWKS

The live round-trip (discovery + code exchange) needs a real IdP and is therefore activated only once a tenant
supplies a verified config; the security-critical validation core runs and is tested here without one.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

import jwt
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.security import create_access_token
from api.services.rbac import write_audit
from core.config import settings

VALID_ROLES = {"admin", "analyst", "approver", "viewer"}


class SsoError(ValueError):
    """A client-facing SSO configuration or login failure."""


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── configuration ────────────────────────────────────────────────────────────
def get_config(session: Session, org_id: str, *, include_secret: bool = False) -> dict | None:
    r = session.execute(text("SELECT * FROM tenant_sso_config WHERE org_id = CAST(:o AS uuid)"),
                        {"o": org_id}).mappings().first()
    if not r:
        return None
    d = dict(r)
    d.pop("scim_token_hash", None)
    if not include_secret:
        d["oidc_client_secret"] = "********" if d.get("oidc_client_secret") else None
    d["scim_configured"] = bool(r["scim_token_hash"])
    return d


def upsert_config(session: Session, org_id: str, *, actor_user_id: str | None, **fields) -> dict:
    """Create or update a tenant's SSO config. Only the provided fields are changed."""
    if "default_role" in fields and fields["default_role"] not in VALID_ROLES:
        raise SsoError(f"default_role must be one of {sorted(VALID_ROLES)}")
    if "protocol" in fields and fields["protocol"] not in ("oidc", "saml"):
        raise SsoError("protocol must be 'oidc' or 'saml'")
    allowed = {"protocol", "enabled", "oidc_issuer", "oidc_client_id", "oidc_client_secret",
               "allowed_email_domain", "jit_provisioning", "default_role", "scim_enabled",
               "saml_idp_entity_id", "saml_idp_sso_url", "saml_idp_x509_cert", "password_login_disabled"}
    cols = {k: v for k, v in fields.items() if k in allowed}
    if "oidc_client_secret" in cols:   # never store the client secret in plaintext
        from core.security.crypto import encrypt
        cols["oidc_client_secret"] = encrypt(cols["oidc_client_secret"])
    exists = session.execute(text("SELECT 1 FROM tenant_sso_config WHERE org_id = CAST(:o AS uuid)"),
                            {"o": org_id}).first()
    if not exists:
        session.execute(text("INSERT INTO tenant_sso_config (org_id) VALUES (CAST(:o AS uuid))"), {"o": org_id})
    if cols:
        sets = ", ".join(f"{k} = :{k}" for k in cols)
        session.execute(text(f"UPDATE tenant_sso_config SET {sets}, updated_at = now() WHERE org_id = CAST(:o AS uuid)"),
                        {**cols, "o": org_id})
    # can't enable a protocol without its essentials
    cfg = session.execute(text("""
        SELECT enabled, protocol, oidc_issuer, oidc_client_id, saml_idp_sso_url, saml_idp_x509_cert
        FROM tenant_sso_config WHERE org_id = CAST(:o AS uuid)
    """), {"o": org_id}).mappings().first()
    if cfg["enabled"]:
        if cfg["protocol"] == "saml" and not (cfg["saml_idp_sso_url"] and cfg["saml_idp_x509_cert"]):
            raise SsoError("SAML IdP SSO URL and signing certificate are required before enabling SSO")
        if cfg["protocol"] != "saml" and not (cfg["oidc_issuer"] and cfg["oidc_client_id"]):
            raise SsoError("issuer and client_id are required before enabling SSO")
    write_audit(session, org_id=org_id, actor_user_id=actor_user_id, action="sso.config_updated",
                target_type="tenant_sso_config", target_id=org_id, detail={"fields": list(cols)})
    session.commit()
    return get_config(session, org_id)


def generate_scim_token(session: Session, org_id: str, *, actor_user_id: str | None) -> dict:
    """Mint a SCIM bearer token (shown once). The IdP presents it on every SCIM provisioning call."""
    raw = "scim_" + secrets.token_urlsafe(32)
    exists = session.execute(text("SELECT 1 FROM tenant_sso_config WHERE org_id = CAST(:o AS uuid)"), {"o": org_id}).first()
    if not exists:
        session.execute(text("INSERT INTO tenant_sso_config (org_id) VALUES (CAST(:o AS uuid))"), {"o": org_id})
    session.execute(text("""
        UPDATE tenant_sso_config SET scim_token_hash = :h, scim_enabled = true, updated_at = now()
        WHERE org_id = CAST(:o AS uuid)
    """), {"h": _hash(raw), "o": org_id})
    write_audit(session, org_id=org_id, actor_user_id=actor_user_id, action="sso.scim_token_issued",
                target_type="tenant_sso_config", target_id=org_id)
    session.commit()
    return {"scim_token": raw, "scim_base_url": f"{settings.APP_BASE_URL.rstrip('/')}/scim/v2"}


def org_for_scim_token(session: Session, token: str) -> str | None:
    r = session.execute(text("""
        SELECT org_id FROM tenant_sso_config WHERE scim_token_hash = :h AND scim_enabled = true
    """), {"h": _hash(token)}).first()
    return str(r[0]) if r else None


# ── OIDC login round-trip ────────────────────────────────────────────────────
def _redirect_uri() -> str:
    return f"{settings.APP_BASE_URL.rstrip('/')}/sso/callback"


def discover(issuer: str) -> dict:
    """Fetch the IdP's OIDC discovery document (authorization/token/jwks endpoints). Needs network + a real IdP."""
    import requests
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def authorize_url(session: Session, org_id: str, state: str) -> str:
    cfg = session.execute(text("""
        SELECT enabled, oidc_issuer, oidc_client_id FROM tenant_sso_config WHERE org_id = CAST(:o AS uuid)
    """), {"o": org_id}).mappings().first()
    if not cfg or not cfg["enabled"]:
        raise SsoError("SSO is not enabled for this organization")
    meta = discover(cfg["oidc_issuer"])
    q = urlencode({"response_type": "code", "client_id": cfg["oidc_client_id"],
                   "redirect_uri": _redirect_uri(), "scope": "openid email profile", "state": state})
    return f"{meta['authorization_endpoint']}?{q}"


def validate_id_token(id_token: str, *, issuer: str, client_id: str, jwks: list[dict] | None = None,
                      jwks_uri: str | None = None, leeway: int = 30) -> dict:
    """Verify an OIDC ID token's signature (RS256 via the IdP's JWKS) and iss/aud/exp claims. PURE + testable:
    pass `jwks` (the IdP's key set) directly in tests; the live path resolves it from `jwks_uri`."""
    header = jwt.get_unverified_header(id_token)
    kid = header.get("kid")
    keyset = jwks
    if keyset is None:
        if not jwks_uri:
            raise SsoError("no JWKS available to validate the token")
        import requests
        keyset = requests.get(jwks_uri, timeout=10).json().get("keys", [])
    match = next((k for k in keyset if k.get("kid") == kid), None) or (keyset[0] if keyset else None)
    if not match:
        raise SsoError("no matching signing key for this token")
    public_key = RSAAlgorithm.from_jwk(json.dumps(match))
    try:
        claims = jwt.decode(id_token, public_key, algorithms=["RS256"], audience=client_id,
                            issuer=issuer, leeway=leeway)
    except jwt.InvalidTokenError as e:
        raise SsoError(f"invalid ID token: {e}") from e
    if not claims.get("email"):
        raise SsoError("the IdP did not return an email claim")
    return claims


def provision_sso_user(session: Session, org_id: str, *, email: str, full_name: str | None,
                       external_id: str | None, default_role: str) -> dict:
    """Find or JIT-create an SSO user (active, no local password). Returns {user_id, email, created}."""
    email = email.strip().lower()
    existing = session.execute(text("""
        SELECT user_id, status FROM users WHERE org_id = CAST(:o AS uuid) AND lower(email) = :e
    """), {"o": org_id, "e": email}).mappings().first()
    if existing:
        session.execute(text("""
            UPDATE users SET status = 'active', auth_provider = 'sso',
              external_id = COALESCE(:x, external_id), full_name = COALESCE(full_name, :n)
            WHERE user_id = :u
        """), {"x": external_id, "n": full_name, "u": str(existing["user_id"])})
        return {"user_id": str(existing["user_id"]), "email": email, "created": False}
    user_id = str(uuid.uuid4())
    role = default_role if default_role in VALID_ROLES else "viewer"
    session.execute(text("""
        INSERT INTO users (user_id, org_id, email, role, full_name, hashed_password, status, auth_provider, external_id, created_at)
        VALUES (CAST(:u AS uuid), CAST(:o AS uuid), :e, :r, :n, NULL, 'active', 'sso', :x, now())
    """), {"u": user_id, "o": org_id, "e": email, "r": role, "n": full_name, "x": external_id})
    rid = session.execute(text("SELECT role_id FROM roles WHERE org_id = CAST(:o AS uuid) AND name = :r"),
                          {"o": org_id, "r": role}).scalar()
    if rid:
        session.execute(text("INSERT INTO user_roles (user_id, role_id) VALUES (CAST(:u AS uuid), CAST(:r AS uuid)) ON CONFLICT DO NOTHING"),
                        {"u": user_id, "r": str(rid)})
    return {"user_id": user_id, "email": email, "created": True}


def discover_by_email(session: Session, email: str) -> dict | None:
    """Resolve a work email to an SSO-enabled tenant by its allowed_email_domain (for the login-screen button)."""
    email = (email or "").strip().lower()
    if "@" not in email:
        return None
    domain = email.split("@", 1)[1]
    r = session.execute(text("""
        SELECT c.org_id, c.protocol, o.name AS org_name
        FROM tenant_sso_config c JOIN organizations o ON o.org_id = c.org_id
        WHERE c.enabled = true AND lower(c.allowed_email_domain) = :d
        LIMIT 1
    """), {"d": domain}).mappings().first()
    return {"org_id": str(r["org_id"]), "protocol": r["protocol"], "org_name": r["org_name"]} if r else None


def login_redirect_url(session: Session, org_id: str, state: str) -> str:
    """Protocol-aware SP-initiated login: OIDC authorize URL or a SAML AuthnRequest redirect."""
    cfg = session.execute(text("""
        SELECT enabled, protocol, oidc_issuer, oidc_client_id, saml_idp_sso_url
        FROM tenant_sso_config WHERE org_id = CAST(:o AS uuid)
    """), {"o": org_id}).mappings().first()
    if not cfg or not cfg["enabled"]:
        raise SsoError("SSO is not enabled for this organization")
    if cfg["protocol"] == "saml":
        from services.governance import saml as saml_svc
        if not cfg["saml_idp_sso_url"]:
            raise SsoError("this organization's SAML IdP is not fully configured")
        return saml_svc.build_authn_request(idp_sso_url=cfg["saml_idp_sso_url"], relay_state=state or org_id)
    # OIDC
    from urllib.parse import urlencode as _q
    if not (cfg["oidc_issuer"] and cfg["oidc_client_id"]):
        raise SsoError("this organization's OIDC IdP is not fully configured")
    meta = discover(cfg["oidc_issuer"])
    return f"{meta['authorization_endpoint']}?" + _q({
        "response_type": "code", "client_id": cfg["oidc_client_id"], "redirect_uri": _redirect_uri(),
        "scope": "openid email profile", "state": state or org_id})


def handle_saml_acs(session: Session, saml_response_b64: str, relay_state: str) -> dict:
    """Validate a SAML Response POSTed to our ACS, JIT-provision the user, and mint our session JWT. IdP-gated."""
    from services.governance import saml as saml_svc
    org_id = relay_state
    cfg = session.execute(text("SELECT * FROM tenant_sso_config WHERE org_id = CAST(:o AS uuid)"),
                          {"o": org_id}).mappings().first()
    if not cfg or not cfg["enabled"] or cfg["protocol"] != "saml":
        raise SsoError("SAML SSO is not enabled for this organization")
    if not cfg["saml_idp_x509_cert"]:
        raise SsoError("this organization's SAML signing certificate is not configured")
    try:
        claims = saml_svc.validate_saml_response(
            saml_response_b64, sp_entity_id=saml_svc.sp_entity_id(), sp_acs_url=saml_svc.acs_url(),
            idp_cert=cfg["saml_idp_x509_cert"])
    except saml_svc.SamlError as e:
        raise SsoError(str(e)) from e
    email = claims["email"]
    if cfg["allowed_email_domain"] and not email.endswith("@" + cfg["allowed_email_domain"].lower()):
        raise SsoError("this email domain is not permitted for single sign-on here")
    if not cfg["jit_provisioning"]:
        exists = session.execute(text("SELECT user_id FROM users WHERE org_id = CAST(:o AS uuid) AND lower(email) = :e AND status='active'"),
                                 {"o": org_id, "e": email}).first()
        if not exists:
            raise SsoError("no account for this user, and JIT provisioning is disabled")
    user = provision_sso_user(session, org_id, email=email, full_name=claims.get("name"),
                              external_id=claims.get("name_id"), default_role=cfg["default_role"])
    write_audit(session, org_id=org_id, actor_user_id=user["user_id"], action="sso.login",
                target_type="user", target_id=user["user_id"], detail={"protocol": "saml", "jit_created": user["created"]})
    session.commit()
    return {"access_token": create_access_token(user_id=user["user_id"], org_id=org_id), "token_type": "bearer"}


def handle_oidc_callback(session: Session, org_id: str, code: str) -> dict:
    """Exchange the auth code, validate the ID token, JIT-provision, and mint our session JWT. IdP-gated."""
    cfg = session.execute(text("SELECT * FROM tenant_sso_config WHERE org_id = CAST(:o AS uuid)"),
                          {"o": org_id}).mappings().first()
    if not cfg or not cfg["enabled"]:
        raise SsoError("SSO is not enabled for this organization")
    meta = discover(cfg["oidc_issuer"])
    import requests
    from core.security.crypto import decrypt
    tok = requests.post(meta["token_endpoint"], timeout=10, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": _redirect_uri(),
        "client_id": cfg["oidc_client_id"], "client_secret": decrypt(cfg["oidc_client_secret"]),
    })
    tok.raise_for_status()
    id_token = tok.json().get("id_token")
    if not id_token:
        raise SsoError("the IdP did not return an id_token")
    claims = validate_id_token(id_token, issuer=cfg["oidc_issuer"], client_id=cfg["oidc_client_id"],
                               jwks_uri=meta.get("jwks_uri"))
    email = claims["email"]
    if cfg["allowed_email_domain"] and not email.lower().endswith("@" + cfg["allowed_email_domain"].lower()):
        raise SsoError("this email domain is not permitted for single sign-on here")
    if not cfg["jit_provisioning"]:
        exists = session.execute(text("SELECT user_id FROM users WHERE org_id = CAST(:o AS uuid) AND lower(email) = :e AND status='active'"),
                                 {"o": org_id, "e": email.lower()}).first()
        if not exists:
            raise SsoError("no account for this user, and JIT provisioning is disabled")
    user = provision_sso_user(session, org_id, email=email, full_name=claims.get("name"),
                              external_id=claims.get("sub"), default_role=cfg["default_role"])
    write_audit(session, org_id=org_id, actor_user_id=user["user_id"], action="sso.login",
                target_type="user", target_id=user["user_id"], detail={"jit_created": user["created"]})
    session.commit()
    return {"access_token": create_access_token(user_id=user["user_id"], org_id=org_id), "token_type": "bearer"}
