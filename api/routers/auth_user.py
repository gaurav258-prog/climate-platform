"""
User authentication endpoints (login sessions, distinct from machine API keys).

POST /v1/auth/login   — email + password → JWT + full profile (roles, permissions, entitlements)
GET  /v1/auth/me      — current user's profile from a Bearer JWT
POST /v1/auth/logout  — stateless no-op (client discards token); logged for audit
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from api.deps import CurrentUser, DbSession
from api.security import create_access_token, token_expires_in_seconds
from api.services.rbac import authenticate, load_user_context, write_audit
from services.governance import totp

router = APIRouter(prefix="/v1/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    email:    str = Field(..., min_length=3)
    password: str = Field(..., min_length=1)
    otp:      Optional[str] = None


def _profile(ctx: dict) -> dict:
    return {
        "user": ctx["user"],
        "org": ctx["org"],
        "roles": ctx["roles"],
        "permissions": ctx["permissions"],
        "entitlements": ctx["entitlements"],
    }


@router.post("/login", summary="Log in with email + password")
def login(body: LoginRequest, session: DbSession, request: Request):
    user = authenticate(session, body.email, body.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_credentials", "message": "Email or password is incorrect."},
        )

    # MFA is mandatory once enrolled — password alone is not enough.
    if user.get("mfa_enrolled_at"):
        if not body.otp:
            raise HTTPException(
                status_code=401,
                detail={"error": "mfa_required", "message": "Enter the 6-digit code from your authenticator app."},
            )
        if not totp.verify(user.get("mfa_secret") or "", body.otp):
            raise HTTPException(
                status_code=401,
                detail={"error": "mfa_invalid", "message": "That code didn't match. Try again."},
            )

    ctx = load_user_context(session, user["user_id"])
    token = create_access_token(user_id=user["user_id"], org_id=user["org_id"])

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
