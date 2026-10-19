"""Shared FastAPI dependencies — DB session, pagination, API key auth."""
from __future__ import annotations

import re
from typing import Annotated, Generator, Optional

from fastapi import Depends, Header, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from core.db.session import get_session as _get_session
from core.errors import UserError

# ── DB session ─────────────────────────────────────────────────────────

def db_session() -> Generator[Session, None, None]:
    with _get_session() as session:
        yield session


# scope="function": the session commits when the route returns, BEFORE the response is sent — a client acting on a
# returned id (an approval request, a filing) at once must find it saved (E138; the default "request" scope committed
# after the response went out)
DbSession = Annotated[Session, Depends(db_session, scope="function")]


# ── Pagination ─────────────────────────────────────────────────────────

def pagination(
    limit:  int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0,   ge=0),
) -> dict:
    return {"limit": limit, "offset": offset}


Pagination = Annotated[dict, Depends(pagination)]


# ── API key auth ───────────────────────────────────────────────────────

_bearer = HTTPBearer(auto_error=False)


def require_customer_id(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)] = None,
    session:     DbSession = None,
) -> str:
    """
    Validate Bearer API key → return customer_id.

    Header:  Authorization: Bearer cp_live_<32hex>

    Keys are created via POST /v1/auth/keys and stored as SHA-256 hashes.
    Raw key is shown exactly once at creation time.
    """
    if not credentials or not credentials.credentials:
        raise UserError("platform.access.no_key")

    from api.auth import validate_api_key
    result = validate_api_key(session, credentials.credentials)

    if not result:
        raise UserError("platform.access.bad_key")

    return result["customer_id"]


CustomerId = Annotated[str, Depends(require_customer_id)]


# ── Tenant ingest-token auth (direct source-system integration) ─────────
# A tenant service account. Token format tlm_live_… ; distinct from user JWTs and legacy cp_live_ keys.

def require_ingest_org(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)] = None,
    session:     DbSession = None,
) -> dict:
    """Validate a Bearer ingest token → {org_id, token_id, org_type, org_name}."""
    raw = credentials.credentials if credentials else None
    if not raw:
        raise UserError("platform.access.no_ingest_token")
    if not raw.startswith("tlm_live_"):
        raise UserError("platform.access.not_ingest_token")
    from api.services.ingest_tokens import validate_token
    res = validate_token(session, raw)
    if not res:
        raise UserError("platform.access.bad_ingest_token")
    return res


IngestOrg = Annotated[dict, Depends(require_ingest_org)]


# ── User JWT auth (login sessions) ──────────────────────────────────────
# Disambiguation: machine API keys start with "cp_live_"; user JWTs never do.

# A RESPONDENT organisation (a supervised entity that does not use Tellumen as a workspace) may only reach the
# supervisory portal's own routes. Enforced here, once, for every protected route — not per router.
RESPONDENT_PATHS = ("/v1/auth/", "/v1/me/supervisors", "/v1/reg-tasks/calendar", "/v1/account", "/v1/onboarding/", "/v1/ingest/tokens")


def get_current_user(
    request: Request,
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)] = None,
    session:     DbSession = None,
) -> dict:
    """
    Validate a Bearer user JWT → return the full user context
    {user, org, roles, permissions, entitlements}.
    """
    token = credentials.credentials if credentials else None
    if not token:
        raise UserError("platform.access.signed_out")
    if token.startswith("cp_live_"):
        raise UserError("platform.access.needs_sign_in")

    from api.security import decode_access_token
    from api.services.rbac import load_user_context

    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise UserError("platform.access.session_expired")

    ctx = load_user_context(session, payload["sub"])
    if not ctx or ctx["user"]["status"] != "active":
        # the same words as an expired session: a sign-in never says whether an account exists or is switched off
        raise UserError("platform.access.session_expired")
    # session revocation: a token minted before revoke-all / password-reset carries a stale version
    if payload.get("tv", 0) != ctx["user"].get("token_version", 0):
        raise UserError("platform.access.session_revoked")
    if (ctx.get("org") or {}).get("plan") == "respondent" and not request.url.path.startswith(RESPONDENT_PATHS):
        raise UserError("platform.access.portal_only")
    return ctx


CurrentUser = Annotated[dict, Depends(get_current_user)]


def require_step_up(ctx: CurrentUser, x_step_up: Optional[str] = Header(None)) -> dict:
    """Gate a sensitive action on a fresh step-up token (from POST /v1/auth/step-up), passed as X-Step-Up."""
    from api.security import decode_access_token
    p = decode_access_token(x_step_up) if x_step_up else None
    if not p or p.get("typ") != "stepup" or p.get("sub") != ctx["user"]["id"]:
        raise UserError("platform.access.step_up")
    return ctx


def require_permission(code: str):
    """Dependency factory: 403 unless the current user holds `code`. The refusal names the permission in the
    customer's words (the admin.permission names, the same as the control center's roles grid), never its code."""
    def _dep(ctx: CurrentUser) -> dict:
        if code not in ctx["permissions"]:
            from core import messages
            name = messages.names().get("admin.permission", {}).get(code)   # every required permission is named (test)
            raise UserError("platform.access.missing_permission", permission=name) if name else UserError("error.forbidden")
        return ctx
    return _dep


# ── Tenant scoping for the sector APIs ─────────────────────────────────

def tenant_resolver(demo_org: str):
    """The caller's organisation: a valid user JWT's org (real tenant isolation); a caller without one sees only the
    sector's public demo organisation — never an org named in the request. One implementation for every sector API."""
    def resolve_org(credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)] = None) -> str:
        token = credentials.credentials if credentials else None
        if token and not token.startswith("cp_live_"):
            from api.security import decode_access_token
            payload = decode_access_token(token)
            if payload and payload.get("org_id"):
                return payload["org_id"]
        return demo_org
    return resolve_org


def own_or_404(session: Session, table: str, id_col: str, target_id: str, org_id: str, label: str) -> None:
    """A record addressed by id is served only to its own organisation; any other caller gets 404 — the same answer as
    for an id that does not exist, so a record's existence is never revealed across tenants. Table and column names
    come from code, never from the request."""
    from sqlalchemy import text as _text
    try:
        row = session.execute(_text(f"SELECT 1 FROM {table} WHERE {id_col} = CAST(:i AS uuid) AND org_id = CAST(:o AS uuid)"),
                              {"i": target_id, "o": org_id}).first()
    except Exception:   # noqa: BLE001 — a malformed id is simply not found
        session.rollback()
        row = None
    if not row:
        raise UserError("platform.access.not_found", thing=label)


def attachment(filename: str) -> str:
    """The Content-Disposition of a download (E111): an ASCII fallback name plus the real name in RFC 5987 `filename*` — a
    header cannot carry a name from the data as-is (a label with '·', a supplier with an accent broke the download)."""
    import unicodedata
    from urllib.parse import quote
    plain = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode()
    plain = re.sub(r'[^A-Za-z0-9._-]+', "-", plain).strip("-") or "download"
    return f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(filename)}"
