"""Passkeys (WebAuthn) + e-signature endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.deps import CurrentUser, DbSession, require_permission
from api.ratelimit import rate_limiter
from services.governance import esign as esign_svc
from services.governance import passkeys as pk
from services.governance import sessions as sess

router = APIRouter(prefix="/v1", tags=["passkeys", "esign"])
_pk_login_limit = rate_limiter(max_calls=30, window_seconds=60)


# ── passkeys: registration (authenticated) ───────────────────────────────────
@router.post("/auth/passkey/register/options")
def pk_reg_options(ctx: CurrentUser, session: DbSession):
    return pk.registration_options(session, user_id=ctx["user"]["id"], email=ctx["user"]["email"],
                                   full_name=ctx["user"].get("full_name"))


class PkRegisterVerify(BaseModel):
    credential: dict
    name: Optional[str] = None


@router.post("/auth/passkey/register/verify")
def pk_reg_verify(body: PkRegisterVerify, ctx: CurrentUser, session: DbSession):
    try:
        return pk.registration_verify(session, user_id=ctx["user"]["id"], credential=body.credential, name=body.name)
    except pk.PasskeyError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})


@router.get("/auth/passkey/credentials")
def pk_list(ctx: CurrentUser, session: DbSession):
    return {"credentials": pk.list_credentials(session, ctx["user"]["id"])}


@router.delete("/auth/passkey/credentials/{credential_id}")
def pk_delete(credential_id: str, ctx: CurrentUser, session: DbSession):
    return {"deleted": pk.delete_credential(session, user_id=ctx["user"]["id"], credential_id=credential_id)}


# ── passkeys: authentication (public) ────────────────────────────────────────
class PkLoginOptions(BaseModel):
    email: str


@router.post("/auth/passkey/login/options")
def pk_login_options(body: PkLoginOptions, session: DbSession, _rl: None = Depends(_pk_login_limit)):
    opts = pk.authentication_options(session, body.email)
    if not opts:
        raise HTTPException(status_code=404, detail={"message": "no passkey is registered for this account"})
    return opts


class PkLoginVerify(BaseModel):
    email: str
    credential: dict


@router.post("/auth/passkey/login/verify")
def pk_login_verify(body: PkLoginVerify, session: DbSession, request: Request):
    try:
        who = pk.authentication_verify(session, email=body.email, credential=body.credential)
    except pk.PasskeyError as e:
        raise HTTPException(status_code=401, detail={"error": "passkey_failed", "message": str(e)})
    return sess.issue_pair(session, user_id=who["user_id"], org_id=who["org_id"],
                           user_agent=request.headers.get("user-agent"),
                           ip=request.client.host if request.client else None)


# ── e-signature ──────────────────────────────────────────────────────────────
class EsignRequestIn(BaseModel):
    title: str
    signer_email: str
    contract_id: Optional[str] = None


@router.post("/esign/requests", status_code=201)
def esign_create(body: EsignRequestIn, session: DbSession, ctx: dict = Depends(require_permission("contracts.manage"))):
    try:
        return esign_svc.request_signature(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                                           title=body.title, signer_email=body.signer_email, contract_id=body.contract_id)
    except esign_svc.EsignError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})


@router.get("/esign/requests")
def esign_list(session: DbSession, ctx: dict = Depends(require_permission("contracts.view"))):
    return {"requests": esign_svc.list_requests(session, ctx["org"]["org_id"])}


class EsignComplete(BaseModel):
    contract_id: Optional[str] = None


@router.post("/esign/requests/{request_id}/complete")
def esign_complete(request_id: str, body: EsignComplete, session: DbSession,
                   ctx: dict = Depends(require_permission("contracts.manage"))):
    try:
        return esign_svc.complete_request(session, org_id=ctx["org"]["org_id"], request_id=request_id,
                                          actor_user_id=ctx["user"]["id"], contract_id=body.contract_id)
    except esign_svc.EsignError as e:
        raise HTTPException(status_code=404, detail={"message": str(e)})
