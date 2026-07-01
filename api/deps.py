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
    return ctx


CurrentUser = Annotated[dict, Depends(get_current_user)]


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
