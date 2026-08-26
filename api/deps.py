"""Shared FastAPI dependencies — DB session, pagination, API key auth."""
from __future__ import annotations

from typing import Annotated, Generator, Optional

from fastapi import Depends, Header, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from core.db.session import get_session as _get_session

# ── DB session ─────────────────────────────────────────────────────────

def db_session() -> Generator[Session, None, None]:
    with _get_session() as session:
        yield session


DbSession = Annotated[Session, Depends(db_session)]


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
        raise HTTPException(
            status_code=401,
            detail={
                "error":   "missing_credentials",
                "message": "Authorization: Bearer <api_key> header required.",
            },
        )

    from api.auth import validate_api_key
    result = validate_api_key(session, credentials.credentials)

    if not result:
        raise HTTPException(
            status_code=401,
            detail={
                "error":   "invalid_api_key",
                "message": "API key is invalid, revoked, or expired.",
            },
        )

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
        raise HTTPException(status_code=401, detail={
            "error": "missing_credentials", "message": "Authorization: Bearer <ingest_token> header required."})
    if not raw.startswith("tlm_live_"):
        raise HTTPException(status_code=401, detail={
            "error": "ingest_token_required",
            "message": "This endpoint needs a tenant ingest token (tlm_live_…), not a user session or legacy key."})
    from api.services.ingest_tokens import validate_token
    res = validate_token(session, raw)
    if not res:
        raise HTTPException(status_code=401, detail={
            "error": "invalid_ingest_token", "message": "Ingest token is invalid, revoked, or expired."})
    return res


IngestOrg = Annotated[dict, Depends(require_ingest_org)]


# ── User JWT auth (login sessions) ──────────────────────────────────────
# Disambiguation: machine API keys start with "cp_live_"; user JWTs never do.

def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)] = None,
    session:     DbSession = None,
) -> dict:
    """
    Validate a Bearer user JWT → return the full user context
    {user, org, roles, permissions, entitlements}.
    """
    token = credentials.credentials if credentials else None
    if not token:
        raise HTTPException(
            status_code=401,
            detail={"error": "missing_credentials", "message": "Authorization: Bearer <token> required."},
        )
    if token.startswith("cp_live_"):
        raise HTTPException(
            status_code=401,
            detail={"error": "user_token_required", "message": "This endpoint requires a user session token, not an API key."},
        )

    from api.security import decode_access_token
    from api.services.rbac import load_user_context

    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_token", "message": "Session token is invalid or expired."},
        )

    ctx = load_user_context(session, payload["sub"])
    if not ctx or ctx["user"]["status"] != "active":
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_token", "message": "User not found or disabled."},
        )
    # session revocation: a token minted before revoke-all / password-reset carries a stale version
    if payload.get("tv", 0) != ctx["user"].get("token_version", 0):
        raise HTTPException(
            status_code=401,
            detail={"error": "session_revoked", "message": "This session has been signed out. Please sign in again."},
        )
    return ctx


CurrentUser = Annotated[dict, Depends(get_current_user)]


def require_step_up(ctx: CurrentUser, x_step_up: Optional[str] = Header(None)) -> dict:
    """Gate a sensitive action on a fresh step-up token (from POST /v1/auth/step-up), passed as X-Step-Up."""
    from api.security import decode_access_token
    p = decode_access_token(x_step_up) if x_step_up else None
    if not p or p.get("typ") != "stepup" or p.get("sub") != ctx["user"]["id"]:
        raise HTTPException(status_code=403,
                            detail={"error": "step_up_required", "message": "Re-authenticate to perform this action."})
    return ctx


def require_permission(code: str):
    """Dependency factory: 403 unless the current user holds `code`."""
    def _dep(ctx: CurrentUser) -> dict:
        if code not in ctx["permissions"]:
            raise HTTPException(
                status_code=403,
                detail={"error": "forbidden", "message": f"Missing permission: {code}"},
            )
        return ctx
    return _dep
