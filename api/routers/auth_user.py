"""
User authentication endpoints (login sessions, distinct from machine API keys).

POST /v1/auth/login   — email + password → JWT + full profile (roles, permissions, entitlements)
GET  /v1/auth/me      — current user's profile from a Bearer JWT
POST /v1/auth/logout  — stateless no-op (client discards token); logged for audit
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.deps import CurrentUser, DbSession
from api.ratelimit import rate_limiter
from api.security import create_access_token, token_expires_in_seconds
from api.services.rbac import AuthError, authenticate, load_user_context, write_audit
from services.governance import account_security as acct
from services.governance import totp

router = APIRouter(prefix="/v1/auth", tags=["Auth"])

_login_limit = rate_limiter(max_calls=30, window_seconds=60)     # 30 login attempts / IP / minute
_forgot_limit = rate_limiter(max_calls=8, window_seconds=300)    # 8 reset requests / IP / 5 min


class LoginRequest(BaseModel):
    email:    str = Field(..., min_length=3)
    password: str = Field(..., min_length=1)
    otp:      Optional[str] = None


class ForgotRequest(BaseModel):
    email: str = Field(..., min_length=3)


class ResetRequest(BaseModel):
    password: str = Field(..., min_length=10)


def _profile(ctx: dict) -> dict:
    return {
        "user": ctx["user"],
        "org": ctx["org"],
        "roles": ctx["roles"],
        "permissions": ctx["permissions"],
        "entitlements": ctx["entitlements"],
    }


@router.post("/login", summary="Log in with email + password")
def login(body: LoginRequest, session: DbSession, request: Request, _rl: None = Depends(_login_limit)):
    try:
        user = authenticate(session, body.email, body.password)
    except AuthError as e:
        raise HTTPException(status_code=401, detail={"error": e.code, "message": e.message})
    if not user:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_credentials", "message": "Email or password is incorrect."},
        )

    # MFA is mandatory once enrolled — password alone is not enough. A one-time backup code also works.
    if user.get("mfa_enrolled_at"):
        if not body.otp:
            raise HTTPException(
                status_code=401,
                detail={"error": "mfa_required", "message": "Enter the 6-digit code from your authenticator app."},
            )
        ok = totp.verify(user.get("mfa_secret") or "", body.otp) or acct.consume_backup_code(session, str(user["user_id"]), body.otp)
        if not ok:
            raise HTTPException(
                status_code=401,
                detail={"error": "mfa_invalid", "message": "That code didn't match. Try a code or a backup code."},
            )

    ctx = load_user_context(session, user["user_id"])
    token = create_access_token(user_id=user["user_id"], org_id=user["org_id"], token_version=user.get("token_version", 0))

    write_audit(
        session,
        org_id=str(user["org_id"]),
        actor_user_id=str(user["user_id"]),
        action="login",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": token_expires_in_seconds(),
        **_profile(ctx),
    }


@router.get("/me", summary="Current user profile")
def me(ctx: CurrentUser):
    return _profile(ctx)


@router.post("/logout", status_code=204, summary="Log out (stateless)")
def logout(ctx: CurrentUser, session: DbSession):
    # JWTs are stateless — the client discards the token. We record the event.
    write_audit(
        session,
        org_id=ctx["org"]["org_id"],
        actor_user_id=ctx["user"]["id"],
        action="logout",
    )
    return None


@router.post("/logout-all", summary="Sign out of all sessions on every device")
def logout_all(ctx: CurrentUser, session: DbSession):
    return acct.revoke_all_sessions(session, user_id=ctx["user"]["id"], org_id=ctx["org"]["org_id"])


@router.post("/mfa/backup-codes", summary="Generate one-time MFA recovery codes (shown once)")
def mfa_backup_codes(ctx: CurrentUser, session: DbSession):
    return {"codes": acct.generate_backup_codes(session, ctx["user"]["id"])}


@router.post("/password/forgot", summary="Request a password-reset link")
def forgot_password(body: ForgotRequest, session: DbSession, _rl: None = Depends(_forgot_limit)):
    # always 200 — never reveals whether the email is registered
    return acct.request_password_reset(session, body.email)


@router.get("/password/reset/{token}", summary="Validate a password-reset link")
def check_reset(token: str, session: DbSession):
    r = acct.get_reset(session, token)
    if not r:
        raise HTTPException(status_code=404, detail={"message": "this reset link is invalid or has expired"})
    return r


@router.post("/password/reset/{token}", summary="Set a new password via a reset link")
def do_reset(token: str, body: ResetRequest, session: DbSession):
    try:
        return acct.complete_password_reset(session, token, body.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})
