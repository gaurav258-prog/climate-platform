"""SSO + SCIM HTTP surface.

  • /v1/sso/config        — a tenant admin configures their own OIDC/SCIM (gated admin.users.manage)
  • /v1/sso/login|callback — the OIDC login round-trip (public; IdP-gated once configured)
  • /scim/v2/Users        — SCIM 2.0 provisioning, bearer-authed with the tenant's SCIM token (no /v1 prefix,
                            because IdPs expect the standard /scim/v2 base URL)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from api.deps import CurrentUser, DbSession, require_permission
from core.config import settings
from services.governance import scim as scim_svc
from services.governance import sso as sso_svc

router = APIRouter(prefix="/v1/sso", tags=["sso"])
scim_router = APIRouter(prefix="/scim/v2", tags=["scim"])

_admin = require_permission("admin.users.manage")


# ── tenant SSO configuration ─────────────────────────────────────────────────
class SsoConfigIn(BaseModel):
    enabled: Optional[bool] = None
    oidc_issuer: Optional[str] = None
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None
    allowed_email_domain: Optional[str] = None
    jit_provisioning: Optional[bool] = None
    default_role: Optional[str] = None
    scim_enabled: Optional[bool] = None


@router.get("/config")
def get_sso_config(session: DbSession, ctx: dict = Depends(_admin)):
    return sso_svc.get_config(session, ctx["org"]["org_id"]) or {"enabled": False, "scim_configured": False}


@router.put("/config")
def put_sso_config(body: SsoConfigIn, session: DbSession, ctx: dict = Depends(_admin)):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        return sso_svc.upsert_config(session, ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"], **fields)
    except sso_svc.SsoError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})


@router.post("/config/scim-token")
def new_scim_token(session: DbSession, ctx: dict = Depends(_admin)):
    return sso_svc.generate_scim_token(session, ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"])


# ── OIDC login round-trip (public; activates once a tenant configures a real IdP) ──
@router.get("/login")
def sso_login(org_id: str, session: DbSession, state: str = ""):
    try:
        return RedirectResponse(url=sso_svc.authorize_url(session, org_id, state or org_id))
    except sso_svc.SsoError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})
    except Exception as e:  # noqa: BLE001 — discovery/network failures shouldn't 500 opaquely
        raise HTTPException(status_code=502, detail={"message": f"identity provider unreachable: {e}"})


@router.get("/callback")
def sso_callback(code: str, session: DbSession, state: str = ""):
    org_id = state  # we set state = org_id on the way out
    try:
        result = sso_svc.handle_oidc_callback(session, org_id, code)
    except sso_svc.SsoError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})
    # hand the session token to the SPA via the URL fragment (never sent to a server / logged)
    base = settings.APP_BASE_URL.rstrip("/")
    return RedirectResponse(url=f"{base}/#sso_token={result['access_token']}")


# ── SCIM 2.0 provisioning (bearer-authed with the tenant's SCIM token) ────────
def scim_org(session: DbSession, authorization: Optional[str] = Header(None)) -> tuple:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    org_id = sso_svc.org_for_scim_token(session, token)
    if not org_id:
        raise HTTPException(status_code=401, detail="invalid SCIM token")
    return session, org_id


def _scim(fn, *args):
    try:
        return fn(*args)
    except scim_svc.ScimError as e:
        return JSONResponse(status_code=e.status, content=e.body())


@scim_router.get("/ServiceProviderConfig")
def scim_spconfig():
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
        "patch": {"supported": True}, "filter": {"supported": True, "maxResults": 200},
        "bulk": {"supported": False}, "changePassword": {"supported": False},
        "sort": {"supported": False}, "etag": {"supported": False},
        "authenticationSchemes": [{"type": "oauthbearertoken", "name": "OAuth Bearer Token"}],
    }


@scim_router.post("/Users", status_code=201)
async def scim_create(request: Request, ctx: tuple = Depends(scim_org)):
    session, org_id = ctx
    return _scim(scim_svc.create_user, session, org_id, await request.json())


@scim_router.get("/Users")
def scim_list(ctx: tuple = Depends(scim_org), filter: Optional[str] = None,
              startIndex: int = 1, count: int = 100):
    session, org_id = ctx
    try:
        return scim_svc.list_users(session, org_id, filter_=filter, start_index=startIndex, count=count)
    except scim_svc.ScimError as e:
        return JSONResponse(status_code=e.status, content=e.body())


@scim_router.get("/Users/{user_id}")
def scim_get(user_id: str, ctx: tuple = Depends(scim_org)):
    session, org_id = ctx
    return _scim(scim_svc.get_user, session, org_id, user_id)


@scim_router.put("/Users/{user_id}")
async def scim_replace(user_id: str, request: Request, ctx: tuple = Depends(scim_org)):
    session, org_id = ctx
    return _scim(scim_svc.replace_user, session, org_id, user_id, await request.json())


@scim_router.patch("/Users/{user_id}")
async def scim_patch(user_id: str, request: Request, ctx: tuple = Depends(scim_org)):
    session, org_id = ctx
    return _scim(scim_svc.patch_user, session, org_id, user_id, await request.json())


@scim_router.delete("/Users/{user_id}", status_code=204)
def scim_delete(user_id: str, ctx: tuple = Depends(scim_org)):
    session, org_id = ctx
    try:
        scim_svc.deactivate_user(session, org_id, user_id)
    except scim_svc.ScimError as e:
        return JSONResponse(status_code=e.status, content=e.body())
    return JSONResponse(status_code=204, content=None)
