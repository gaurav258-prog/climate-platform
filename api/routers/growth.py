"""Growth surface — self-serve signup (public) and billing (plans / seats / invoices)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.deps import CurrentUser, DbSession, require_permission
from api.ratelimit import rate_limiter
from services.governance import billing
from services.governance import sessions as sess
from services.governance import signup as signup_svc

router = APIRouter(prefix="/v1", tags=["growth"])
_signup_limit = rate_limiter(max_calls=5, window_seconds=3600)


class SignupIn(BaseModel):
    company_name: str
    org_type: str
    country: str
    admin_email: str
    admin_full_name: Optional[str] = None
    password: str
    sandbox: Optional[bool] = False


@router.post("/signup", summary="Create a trial workspace (self-serve)")
def signup(body: SignupIn, session: DbSession, request: Request, _rl: None = Depends(_signup_limit)):
    try:
        res = signup_svc.self_serve_signup(
            session, company_name=body.company_name, org_type=body.org_type, country=body.country,
            admin_email=body.admin_email, admin_full_name=body.admin_full_name or body.admin_email.split("@")[0],
            password=body.password, sandbox=bool(body.sandbox))
    except signup_svc.SignupError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})
    pair = sess.issue_pair(session, user_id=res["admin_user_id"], org_id=res["org_id"],
                           user_agent=request.headers.get("user-agent"),
                           ip=request.client.host if request.client else None)
    return {**pair, "org_id": res["org_id"]}


@router.get("/billing", summary="Current subscription, seat usage, plans, and invoices")
def get_billing(ctx: CurrentUser, session: DbSession):
    return billing.get_billing(session, ctx["org"]["org_id"])


class PlanIn(BaseModel):
    plan: str


@router.put("/billing/plan", summary="Change plan")
def change_plan(body: PlanIn, session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    try:
        return billing.change_plan(session, ctx["org"]["org_id"], plan=body.plan, actor_user_id=ctx["user"]["id"])
    except billing.BillingError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})
