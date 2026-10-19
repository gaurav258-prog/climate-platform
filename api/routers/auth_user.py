"""
User authentication endpoints (login sessions, distinct from machine API keys).

POST /v1/auth/login   — email + password → JWT + full profile (roles, permissions, entitlements)
GET  /v1/auth/me      — current user's profile from a Bearer JWT
GET  /v1/auth/me/money — the currency the org's screens show money in (presentation currency + rates)
POST /v1/auth/logout  — stateless no-op (client discards token); logged for audit
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text as _sql

from api.deps import CurrentUser, DbSession
from api.ratelimit import rate_limiter
from api.security import create_access_token, token_expires_in_seconds
from api.services.rbac import authenticate, load_user_context, write_audit
from core.errors import UserError
from services.governance import account_security as acct
from services.governance import sessions as sess
from services.governance import totp

router = APIRouter(prefix="/v1/auth", tags=["Auth"])
logger = logging.getLogger(__name__)

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
    # A locked account or one whose organisation signs in through single sign-on is refused by authenticate() with
    # a catalogue code (api/services/rbac.py AuthError). The three refusals below keep their machine codes because
    # the sign-in screen branches on them (web/src/pages/Login.tsx: mfa_required opens the code field); their words
    # are customer words, and a wrong e-mail and a wrong password get the same one.
    user = authenticate(session, body.email, body.password)
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
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    refresh = sess.issue_refresh(session, user_id=str(user["user_id"]), org_id=str(user["org_id"]), user_agent=ua, ip=ip)

    write_audit(session, org_id=str(user["org_id"]), actor_user_id=str(user["user_id"]),
                action="login", ip=ip, user_agent=ua)

    return {
        "access_token": token,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": token_expires_in_seconds(),
        **_profile(ctx),
    }


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", summary="Rotate a refresh token for a fresh access token")
def refresh(body: RefreshRequest, session: DbSession, request: Request):
    try:
        return sess.rotate(session, body.refresh_token,
                           user_agent=request.headers.get("user-agent"),
                           ip=request.client.host if request.client else None)
    except sess.SessionError as e:
        logger.warning("refresh refused: %s", e)          # a reused token signs every session out: worth the log
        raise UserError("platform.access.session_expired") from e


@router.get("/sessions", summary="List active sessions on this account")
def sessions_list(ctx: CurrentUser, session: DbSession):
    return {"sessions": sess.list_sessions(session, ctx["user"]["id"])}


@router.delete("/sessions/{token_id}", summary="Revoke one session")
def session_revoke(token_id: str, ctx: CurrentUser, session: DbSession):
    return {"revoked": sess.revoke_session(session, user_id=ctx["user"]["id"], token_id=token_id)}


@router.get("/me", summary="Current user profile")
def me(ctx: CurrentUser):
    return _profile(ctx)


@router.get("/me/money", summary="The currency this organisation's screens show money in, with the rates used")
def me_money(ctx: CurrentUser, session: DbSession):
    from services.governance.display_currency import view
    return view(session, ctx["org"]["org_id"])


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
    sess.revoke_all(session, user_id=ctx["user"]["id"])              # revoke refresh tokens
    return acct.revoke_all_sessions(session, user_id=ctx["user"]["id"], org_id=ctx["org"]["org_id"])  # + bump access version


@router.post("/mfa/backup-codes", summary="Generate one-time MFA recovery codes (shown once)")
def mfa_backup_codes(ctx: CurrentUser, session: DbSession):
    return {"codes": acct.generate_backup_codes(session, ctx["user"]["id"])}


class StepUpRequest(BaseModel):
    password: str
    otp: Optional[str] = None


@router.post("/step-up", summary="Re-authenticate for a sensitive action (step-up)")
def step_up(body: StepUpRequest, ctx: CurrentUser, session: DbSession):
    from api.security import create_step_up_token, verify_password
    row = session.execute(
        _sql("SELECT hashed_password, mfa_secret, mfa_enrolled_at FROM users WHERE user_id = CAST(:u AS uuid)"),
        {"u": ctx["user"]["id"]}).mappings().first()
    if not verify_password(body.password, row["hashed_password"]):
        raise UserError("platform.signin.step_up_password")
    if row["mfa_enrolled_at"] and not (totp.verify(row["mfa_secret"] or "", body.otp or "")
                                       or acct.consume_backup_code(session, ctx["user"]["id"], body.otp or "")):
        raise UserError("platform.signin.step_up_code")
    return {"step_up_token": create_step_up_token(ctx["user"]["id"])}


@router.post("/password/forgot", summary="Request a password-reset link")
def forgot_password(body: ForgotRequest, session: DbSession, _rl: None = Depends(_forgot_limit)):
    # always 200 — never reveals whether the email is registered
    return acct.request_password_reset(session, body.email)


@router.get("/password/reset/{token}", summary="Validate a password-reset link")
def check_reset(token: str, session: DbSession):
    r = acct.get_reset(session, token)
    if not r:
        raise UserError("platform.reset.link_invalid")
    return r


@router.post("/password/reset/{token}", summary="Set a new password via a reset link")
def do_reset(token: str, body: ResetRequest, session: DbSession):
    # ResetRequest refuses a password shorter than ten characters before this runs, so the one refusal left is the link
    try:
        return acct.complete_password_reset(session, token, body.password)
    except ValueError as e:
        logger.info("password reset refused: %s", e)
        raise UserError("platform.reset.link_invalid", status=400) from e
