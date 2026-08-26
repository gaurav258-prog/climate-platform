"""Client-onboarding lifecycle HTTP surface.

Three audiences, three auth models:
  • operator endpoints  (/v1/onboarding/intakes/*)   — gated on `onboarding.manage` (platform operators)
  • client form         (/v1/onboarding/form/{token}) — token-authenticated, no account yet
  • activation          (/v1/onboarding/activate/*)   — token-authenticated, sets password + enrols MFA

Thin skin over services.governance.client_onboarding, which owns the state machine.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from api.deps import DbSession, require_permission
from services.governance import client_onboarding as ob

router = APIRouter(prefix="/v1/onboarding", tags=["onboarding"])

_manage = require_permission("onboarding.manage")


# ── models ───────────────────────────────────────────────────────────────────
class IntakeCreate(BaseModel):
    company_name: str
    org_type: str
    contact_email: str
    contact_name: Optional[str] = None
    country: Optional[str] = None
    region: str = "EU"
    legal_name: Optional[str] = None
    lei: Optional[str] = None
    filing_contact_email: Optional[str] = None
    modules: Optional[List[str]] = None
    notes: Optional[str] = None


class RosterMember(BaseModel):
    email: str
    full_name: Optional[str] = None
    role: str = "viewer"


class IntakeFormSubmit(BaseModel):
    company_name: Optional[str] = None
    country: Optional[str] = None
    region: str = "EU"
    legal_name: Optional[str] = None
    lei: Optional[str] = None
    filing_contact_email: Optional[str] = None
    aum_eur: Optional[float] = None
    employees: Optional[int] = None
    contact_name: Optional[str] = None
    modules: Optional[List[str]] = None
    roster: List[RosterMember] = []


class PasswordSet(BaseModel):
    password: str


class MfaConfirm(BaseModel):
    code: str


def _oops(e: ob.OnboardingError) -> HTTPException:
    return HTTPException(status_code=400, detail={"message": str(e)})


# ── operator: intake management ──────────────────────────────────────────────
@router.post("/intakes", status_code=201)
def create_intake(body: IntakeCreate, session: DbSession, ctx: dict = Depends(_manage)):
    try:
        return ob.create_intake(
            session, actor_user_id=ctx["user"]["id"], actor_org_id=ctx["org"]["org_id"],
            company_name=body.company_name, org_type=body.org_type, contact_email=str(body.contact_email),
            contact_name=body.contact_name, country=body.country, region=body.region,
            legal_name=body.legal_name, lei=body.lei, filing_contact_email=body.filing_contact_email,
            modules=body.modules, notes=body.notes,
        )
    except ob.OnboardingError as e:
        raise _oops(e)


@router.get("/intakes")
def list_intakes(session: DbSession, ctx: dict = Depends(_manage)):
    return {"intakes": ob.list_intakes(session)}


@router.get("/intakes/{intake_id}")
def get_intake(intake_id: str, session: DbSession, ctx: dict = Depends(_manage)):
    row = ob.get_intake(session, intake_id)
    if not row:
        raise HTTPException(status_code=404, detail={"message": "intake not found"})
    return row


@router.post("/intakes/{intake_id}/provision")
def provision(intake_id: str, session: DbSession, ctx: dict = Depends(_manage)):
    try:
        return ob.provision_from_intake(session, actor_user_id=ctx["user"]["id"], intake_id=intake_id)
    except ob.OnboardingError as e:
        raise _oops(e)


@router.post("/intakes/{intake_id}/resend")
def resend(intake_id: str, session: DbSession, ctx: dict = Depends(_manage)):
    try:
        return ob.resend_activation(session, intake_id=intake_id, actor_user_id=ctx["user"]["id"])
    except ob.OnboardingError as e:
        raise _oops(e)


@router.post("/intakes/{intake_id}/documents", status_code=201)
async def upload_intake_document(
    intake_id: str, session: DbSession, ctx: dict = Depends(_manage),
    file: UploadFile = File(...), kind: str = Form("other"), title: str = Form(""),
    to_vault: bool = Form(False), contract_type: str = Form(None),
):
    data = await file.read()
    try:
        return ob.add_intake_document(
            session, intake_id, kind=kind, title=title or file.filename,
            filename=file.filename or "upload", content_type=file.content_type or "application/octet-stream",
            data=data, to_vault=to_vault, contract_type=contract_type,
        )
    except ob.OnboardingError as e:
        raise _oops(e)


# ── client: the tokenized intake form (no account yet) ───────────────────────
@router.get("/form/{token}")
def load_form(token: str, session: DbSession):
    row = ob.get_intake_by_token(session, token)
    if not row:
        raise HTTPException(status_code=404, detail={"message": "this onboarding link is invalid or has expired"})
    return row


@router.put("/form/{token}")
def submit_form(token: str, body: IntakeFormSubmit, session: DbSession):
    try:
        return ob.submit_intake_form(session, token, body.model_dump())
    except ob.OnboardingError as e:
        raise _oops(e)


@router.post("/form/{token}/documents", status_code=201)
async def upload_form_document(
    token: str, session: DbSession,
    file: UploadFile = File(...), kind: str = Form("other"), title: str = Form(""),
    to_vault: bool = Form(False), contract_type: str = Form(None),
):
    intake = ob.get_intake_by_token(session, token)
    if not intake:
        raise HTTPException(status_code=404, detail={"message": "this onboarding link is invalid or has expired"})
    data = await file.read()
    try:
        return ob.add_intake_document(
            session, str(intake["intake_id"]), kind=kind, title=title or file.filename,
            filename=file.filename or "upload", content_type=file.content_type or "application/octet-stream",
            data=data, to_vault=to_vault, contract_type=contract_type,
        )
    except ob.OnboardingError as e:
        raise _oops(e)


# ── user: activation (set password + enrol MFA) ──────────────────────────────
@router.get("/activate/{token}")
def load_activation(token: str, session: DbSession):
    a = ob.get_activation(session, token)
    if not a:
        raise HTTPException(status_code=404, detail={"message": "this activation link is invalid or has expired"})
    return a


@router.post("/activate/{token}/password")
def set_password(token: str, body: PasswordSet, session: DbSession):
    try:
        return ob.set_activation_password(session, token, body.password)
    except ob.OnboardingError as e:
        raise _oops(e)


@router.post("/activate/{token}/mfa/begin")
def mfa_begin(token: str, session: DbSession):
    try:
        return ob.begin_mfa_enrollment(session, token)
    except ob.OnboardingError as e:
        raise _oops(e)


@router.post("/activate/{token}/mfa/confirm")
def mfa_confirm(token: str, body: MfaConfirm, session: DbSession):
    try:
        return ob.confirm_mfa_enrollment(session, token, body.code)
    except ob.OnboardingError as e:
        raise _oops(e)
