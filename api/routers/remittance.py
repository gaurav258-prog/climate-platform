"""Governed remittance — sharing an evidence pack onward, and what each side sees of it.

  • supervisor    /v1/supervisor/...      issue, list, revoke, access log; in-product recipient list + download
  • entity        /v1/me/supervisors/remittances   the supervised entity sees where its case file went
  • recipient     /v1/remit/{token}       bearer-link view and download — no login; every access logged
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import text

from api.deps import CurrentUser, DbSession, attachment
from api.routers.supervisor import Supervisor, _in_scope, _need
from core import messages
from core.config import settings
from core.errors import UserError
from services.supervision import remittance as R
from services.supervision.evidence import section_title

router = APIRouter(tags=["Supervisor"])


def _who(request: Request, ctx: Optional[dict] = None) -> dict:
    fwd = request.headers.get("x-forwarded-for")
    ip = (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None))
    return {"user_id": (ctx or {}).get("user", {}).get("id"), "org_id": ((ctx or {}).get("org") or {}).get("org_id"), "ip": ip, "user_agent": request.headers.get("user-agent")}


def _file(fmt: str, data: bytes, d: dict) -> Response:
    stem = f"remittance-{d['reference']}"
    if fmt == "pdf":
        return Response(content=data, media_type="application/pdf", headers={"Content-Disposition": attachment(f"{stem}.pdf")})
    return Response(content=data, media_type="application/json", headers={"Content-Disposition": attachment(f"{stem}.json")})


# ── supervisor ──────────────────────────────────────────────────────────────────────────────────────────────
class RemitCreate(BaseModel):
    recipient_kind: str
    recipient_name: str
    recipient_email: Optional[str] = None
    recipient_org_id: Optional[str] = None
    purpose: str
    legal_basis: Optional[str] = None
    sections: Optional[list[str]] = None
    expires_in_days: Optional[int] = None
    max_downloads: Optional[int] = None


@router.get("/v1/supervisor/remittance/config", summary="Recipient kinds, expiry limits and the sections a remittance can carry")
def remit_config(session: DbSession, ctx: Supervisor):
    _need(ctx, "supervisor.remit")
    bodies = session.execute(text("SELECT org_id::text AS org_id, name FROM organizations WHERE type = 'regulator' AND org_id <> CAST(:o AS uuid) ORDER BY name"),
                             {"o": ctx["org"]["org_id"]}).mappings().all()
    cfg = R.config()
    return {"recipient_kinds": cfg["recipient_kinds"], "default_expiry_days": cfg["default_expiry_days"], "max_expiry_days": cfg["max_expiry_days"],
            "default_max_downloads": cfg["default_max_downloads"], "sections": R.SECTIONS, "section_labels": {s: section_title(s) for s in R.SECTIONS},
            "bodies_on_tellumen": [dict(b) for b in bodies], "notice": cfg["notice"], "about": messages.render("supervision.desk.remit.about")}


@router.post("/v1/supervisor/entity/{org_id}/evidence-packs/{pack_id}/remit", status_code=201, summary="Remit this evidence pack onward under a governed share")
def remit_pack(org_id: str, pack_id: str, body: RemitCreate, session: DbSession, ctx: Supervisor):
    _need(ctx, "supervisor.remit")
    if not _in_scope(session, ctx, org_id):
        raise UserError("error.not_found")
    out = R.create(session, regulator_org_id=ctx["org"]["org_id"], regulator_name=ctx["org"].get("name") or "", pack_id=pack_id, recipient_kind=body.recipient_kind,
                   recipient_name=body.recipient_name, recipient_email=body.recipient_email, recipient_org_id=body.recipient_org_id, purpose=body.purpose,
                   legal_basis_text=body.legal_basis, sections=body.sections, expires_in_days=body.expires_in_days, max_downloads=body.max_downloads,
                   actor=ctx["user"], link_base=settings.APP_BASE_URL)      # a refusal is a catalogue code (R.RemittanceError)
    session.commit()
    return out


@router.get("/v1/supervisor/entity/{org_id}/remittances", summary="Remittances issued on this entity's case files")
def entity_remittances(org_id: str, session: DbSession, ctx: Supervisor):
    _need(ctx, "supervisor.evidence.export")
    if not _in_scope(session, ctx, org_id):
        raise UserError("error.not_found")
    return {"remittances": R.list_for_regulator(session, ctx["org"]["org_id"], org_id)}


@router.get("/v1/supervisor/remittances", summary="Every remittance this authority has issued")
def all_remittances(session: DbSession, ctx: Supervisor):
    _need(ctx, "supervisor.evidence.export")
    return {"remittances": R.list_for_regulator(session, ctx["org"]["org_id"])}


class Revoke(BaseModel):
    reason: Optional[str] = None


@router.post("/v1/supervisor/remittances/{remittance_id}/revoke", summary="Revoke a remittance: the link stops working at once")
def revoke_remittance(remittance_id: str, body: Revoke, session: DbSession, ctx: Supervisor):
    _need(ctx, "supervisor.remit")
    if not R.revoke(session, regulator_org_id=ctx["org"]["org_id"], remittance_id=remittance_id, actor=ctx["user"], reason=body.reason):
        raise UserError("error.not_found")
    session.commit()
    return {"ok": True}


@router.get("/v1/supervisor/remittances/{remittance_id}/access-log", summary="Every view and download of one remittance")
def remittance_access_log(remittance_id: str, session: DbSession, ctx: Supervisor):
    _need(ctx, "supervisor.evidence.export")
    return {"accesses": R.access_log(session, ctx["org"]["org_id"], remittance_id)}


@router.get("/v1/supervisor/remittances/received", summary="Case files other authorities remitted to this body")
def received(session: DbSession, ctx: Supervisor):
    return {"remittances": R.list_received(session, ctx["org"]["org_id"])}


@router.get("/v1/supervisor/remittances/received/{remittance_id}.{fmt}", summary="Download a remittance received in-product (logged, counted)")
# declared before the plain open route: "{id}.pdf" would otherwise be read as an id
def received_download(remittance_id: str, fmt: str, request: Request, session: DbSession, ctx: Supervisor):
    status, data, d = R.download(session, fmt=fmt, remittance_id=remittance_id, recipient_org_id=ctx["org"]["org_id"], who=_who(request, ctx))
    session.commit()
    _served(status)
    return _file(fmt, data, d)


@router.get("/v1/supervisor/remittances/received/{remittance_id}", summary="Open a remittance received in-product (logged)")
def received_open(remittance_id: str, request: Request, session: DbSession, ctx: Supervisor):
    d = R.open_remittance(session, remittance_id=remittance_id, recipient_org_id=ctx["org"]["org_id"], who=_who(request, ctx))
    if not d:
        raise UserError("error.not_found")
    session.commit()
    return d


# ── supervised entity ───────────────────────────────────────────────────────────────────────────────────────
@router.get("/v1/me/supervisors/remittances", summary="Where my supervisors have remitted my case file: to whom, why, under what basis, until when")
def my_remittances(session: DbSession, ctx: CurrentUser):
    from core import messages
    about = messages.render("supervision.respondent.shared_onward")
    return {"remittances": R.list_for_entity(session, ctx["org"]["org_id"]),
            "about": {"code": about["code"], "label": about["label"], "detail": about["detail"]}}


# ── recipient (bearer link) ─────────────────────────────────────────────────────────────────────────────────
_GONE = {"expired": "supervision.desk.remit.expired", "revoked": "supervision.desk.remit.revoked", "exhausted": "supervision.desk.remit.exhausted"}


def _served(status: str) -> None:
    """A download that was not served, in customer words: unknown → not found; expired, revoked, exhausted → gone (410).
    The refused access is already logged (R.download records it before answering)."""
    if status == "unknown":
        raise UserError("error.not_found")
    if status != "ok":
        raise UserError(_GONE[status])


@router.get("/v1/remit/{token}", summary="Open a remitted case file by its link (no login; every access is logged)")
def open_by_token(token: str, request: Request, session: DbSession):
    d = R.open_remittance(session, token=token, who=_who(request))
    if not d:
        raise UserError("error.not_found")
    session.commit()
    return d


@router.get("/v1/remit/{token}/download.{fmt}", summary="Download the remitted document (watermarked PDF or scoped JSON)")
def download_by_token(token: str, fmt: str, request: Request, session: DbSession):
    status, data, d = R.download(session, fmt=fmt, token=token, who=_who(request))
    session.commit()
    _served(status)
    return _file(fmt, data, d)
