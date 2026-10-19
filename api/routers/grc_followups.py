"""Assurance-pack shares with the auditor (filing-scoped + public link) and the third-party register."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel

from api.deps import CurrentUser, DbSession, attachment, require_permission
from core import messages
from core.config import settings
from core.errors import UserError
from services.governance import assurance_share as AS
from services.intelligence import third_parties as TP

router = APIRouter(tags=["Governance"])
# why a share no longer serves its pack (assurance_share.status_of, and a pack that cannot be built), in the catalogue
GONE = {"expired": "filings.share.expired", "revoked": "filings.share.revoked", "exhausted": "filings.share.exhausted",
        "unavailable": "filings.share.unavailable"}


def _who(request: Request) -> dict:
    fwd = request.headers.get("x-forwarded-for")
    return {"ip": fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None), "user_agent": request.headers.get("user-agent")}


# ── assurance shares ────────────────────────────────────────────────────────────────────────────────────────
class ShareCreate(BaseModel):
    recipient_name: str
    recipient_email: str
    purpose: str
    expires_in_days: Optional[int] = None
    max_downloads: Optional[int] = None


@router.post("/v1/filings/{filing_id}/assurance-shares", status_code=201, summary="Share this filing's assurance pack with the auditor under a governed link")
def share_pack(filing_id: str, body: ShareCreate, session: DbSession, ctx: dict = Depends(require_permission("reports.publish"))):
    out = AS.create(session, org_id=ctx["org"]["org_id"], org_name=ctx["org"].get("name") or "", filing_id=filing_id, recipient_name=body.recipient_name, recipient_email=body.recipient_email,
                    purpose=body.purpose, expires_in_days=body.expires_in_days, max_downloads=body.max_downloads, actor=ctx["user"], link_base=settings.APP_BASE_URL)
    session.commit()
    return out


@router.get("/v1/filings/{filing_id}/assurance-shares", summary="Shares of this filing's assurance pack and every access to them")
def list_shares(filing_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return {"shares": AS.list_for_filing(session, ctx["org"]["org_id"], filing_id)}


@router.post("/v1/assurance-shares/{share_id}/revoke", summary="Revoke a share: the link stops working at once")
def revoke_share(share_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.publish"))):
    if not AS.revoke(session, org_id=ctx["org"]["org_id"], share_id=share_id, actor=ctx["user"]):
        raise UserError("filing.share.not_active")
    session.commit()
    return {"ok": True}


@router.get("/v1/assurance/{token}", summary="Open a shared assurance pack by its link (no login; logged)")
def open_share(token: str, request: Request, session: DbSession):
    d = AS.open_share(session, token, _who(request))
    if not d:
        raise UserError("filings.share.unknown")
    session.commit()
    # the auditor reads the report by its name and, when the share no longer serves the pack, why — in customer words
    from services.governance.admin_view import report_name
    return {**d, "report": report_name(d["framework"]),
            "contents": messages.render("filings.share.contents", organisation=d["organisation"]),
            "state": messages.render(GONE[d["status"]], organisation=d["organisation"]) if d["status"] in GONE else None}


@router.get("/v1/assurance/{token}/download.zip", summary="Download the shared assurance pack (logged, counted)")
def download_share(token: str, request: Request, session: DbSession):
    status, built, d = AS.download(session, token, _who(request))
    session.commit()
    if status == "unknown":
        raise UserError("filings.share.unknown")
    if status != "ok":
        raise UserError(GONE[status], organisation=d.get("organisation") or "")
    name, blob = built
    return Response(content=blob, media_type="application/zip", headers={"Content-Disposition": attachment(f"{name}")})


# ── third parties ───────────────────────────────────────────────────────────────────────────────────────────
class ThirdPartyCreate(BaseModel):
    name: str
    kind: str
    service: Optional[str] = None
    criticality: str = "important"
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    country: Optional[str] = None
    contract_ref: Optional[str] = None
    note: Optional[str] = None


@router.get("/v1/third-parties", summary="The third-party register with each party's physical exposure at the engine's score")
def third_parties(session: DbSession, ctx: CurrentUser, scenario: str = "baseline", horizon: str = "current"):
    v = TP.view(session, ctx["org"]["org_id"], scenario, horizon)
    v["can_edit"] = "supply.locations.write" in ctx["permissions"]
    return v


@router.post("/v1/third-parties", status_code=201, summary="Add a third party by address or coordinates → located and scored")
def add_third_party(body: ThirdPartyCreate, session: DbSession, ctx: dict = Depends(require_permission("supply.locations.write"))):
    try:
        out = TP.add(session, org_id=ctx["org"]["org_id"], name=body.name, kind=body.kind, service=body.service, criticality=body.criticality, address=body.address, lat=body.latitude, lon=body.longitude,
                     country=body.country, contract_ref=body.contract_ref, note=body.note, actor_user_id=ctx["user"]["id"])
    except TP.ThirdPartyError as e:
        raise UserError(e.code, **e.params) from e
    session.commit()
    return out


@router.delete("/v1/third-parties/{third_party_id}", summary="End a third-party relationship (kept on the audit trail)")
def end_third_party(third_party_id: str, session: DbSession, ctx: dict = Depends(require_permission("supply.locations.write"))):
    if not TP.end(session, org_id=ctx["org"]["org_id"], third_party_id=third_party_id, actor_user_id=ctx["user"]["id"]):
        raise UserError("error.not_found")
    session.commit()
    return {"ok": True}


@router.get("/v1/third-parties/register.csv", summary="Export the third-party register with exposure")
def third_parties_csv(session: DbSession, ctx: CurrentUser):
    return Response(content=TP.register_csv(TP.view(session, ctx["org"]["org_id"])), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="third-party-register.csv"'})
