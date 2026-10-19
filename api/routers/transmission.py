"""Transmission — submission case & regulator-communication API."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import services.governance.transmission as R
from api.deps import DbSession, require_permission
from core.errors import UserError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/transmission", tags=["Transmission"])


def _case_view(c: dict) -> dict:
    """A case with its report named (no legal reference on the main screen)."""
    from services.transmission.service import report_name
    return {**c, "framework_name": report_name(c.get("framework"))}


class CaseOpen(BaseModel):
    regulator: str = Field(..., min_length=1, max_length=200)
    filing_id: Optional[str] = None
    reference: Optional[str] = Field(None, max_length=200)


class StageBody(BaseModel):
    stage: str


class MessageBody(BaseModel):
    direction: str
    author: str = Field(..., max_length=120)
    body: str = Field(..., min_length=1, max_length=4000)
    attachment_ref: Optional[str] = Field(None, max_length=200)


@router.get("/cases", summary="Submission cases")
def cases(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return {"cases": [_case_view(c) for c in R.list_cases(session, ctx["org"]["org_id"])]}


@router.get("/cases/for-filing/{filing_id}", summary="The transmission case linked to a filing (or null)")
def case_for_filing(filing_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return {"case": R.case_for_filing(session, ctx["org"]["org_id"], filing_id)}


@router.get("/cases/{case_id}", summary="One case with its communication thread")
def case(case_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    c = R.get_case(session, ctx["org"]["org_id"], case_id)
    if not c:
        raise UserError("admin.transmission.case_not_found")
    return _case_view(c)


@router.post("/cases", status_code=201, summary="Open a submission case")
def open_case(body: CaseOpen, session: DbSession, ctx: dict = Depends(require_permission("reports.publish"))):
    # a refusal is a catalogue error (R.CaseError)
    return R.open_case(session, ctx["org"]["org_id"], ctx["user"]["id"],
                       regulator=body.regulator, filing_id=body.filing_id, reference=body.reference)


@router.post("/cases/{case_id}/stage", summary="Advance the case stage")
def stage(case_id: str, body: StageBody, session: DbSession,
          ctx: dict = Depends(require_permission("reports.publish"))):
    # a refusal is a catalogue error (R.CaseError)
    return R.advance_stage(session, ctx["org"]["org_id"], case_id, ctx["user"]["id"], body.stage)


@router.post("/cases/{case_id}/message", status_code=201, summary="Log a message on the case")
def message(case_id: str, body: MessageBody, session: DbSession,
            ctx: dict = Depends(require_permission("approvals.create"))):
    # a refusal is a catalogue error (R.CaseError)
    return R.post_message(session, ctx["org"]["org_id"], case_id, ctx["user"]["id"],
                          direction=body.direction, author=body.author, body=body.body,
                          attachment_ref=body.attachment_ref)


# ── Sending filings through a channel ─────────────────────────────────────────────────────────────────────
class SendBody(BaseModel):
    channel_id: str
    format: Optional[str] = None


class ReceiptBody(BaseModel):
    receipt_ref: str = Field(..., min_length=1, max_length=200)
    note: Optional[str] = None


@router.get("/channels", summary="Per framework: the channel the mandate prescribes, the Tellumen channel where your supervisor is on the platform, and readiness")
def channels(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.transmission.service import channels_for
    return channels_for(session, ctx["org"]["org_id"])


@router.get("/sends", summary="Every transmission of this organisation, newest first")
def sends(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.transmission.service import list_for_org, worker
    return {"transmissions": list_for_org(session, ctx["org"]["org_id"]), "worker": worker(session)}


@router.post("/filings/{filing_id}/send", status_code=201, summary="Transmit an attested filing through a channel (runs on the worker; receipt recorded)")
def send_filing(filing_id: str, body: SendBody, session: DbSession, ctx: dict = Depends(require_permission("reports.publish"))):
    from api.services.rbac import write_audit
    from services.tasks.jobs import submit
    from services.transmission.service import create
    org_id = ctx["org"]["org_id"]
    try:          # an unattested filing, an unknown channel or format: catalogue errors from create
        t = create(session, org_id=org_id, filing_id=filing_id, channel_id=body.channel_id, fmt=body.format, by_user_id=ctx["user"]["id"])
    except ValueError as e:             # the export could not be produced: the cause to the log
        logger.warning("transmission not prepared for %s: %s", filing_id, e)
        raise UserError("admin.transmission.not_prepared") from e
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="filing.transmit", target_type="regulatory_filing", target_id=filing_id,
                detail={"transmission_id": t["transmission_id"], "channel_id": body.channel_id, "format": t["format"]})
    session.commit()
    job = submit("transmission.send", t["transmission_id"])
    return {**t, "job": job}


@router.get("/filings/{filing_id}/sends", summary="Transmissions of one filing")
def filing_sends(filing_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.transmission.service import list_for_filing, worker
    return {"transmissions": list_for_filing(session, ctx["org"]["org_id"], filing_id), "worker": worker(session)}


@router.post("/sends/{transmission_id}/receipt", summary="Record the authority's reference for a transmission made outside the platform")
def receipt(transmission_id: str, body: ReceiptBody, session: DbSession, ctx: dict = Depends(require_permission("reports.publish"))):
    from api.services.rbac import write_audit
    from services.transmission.service import record_receipt
    org_id = ctx["org"]["org_id"]
    out = record_receipt(session, org_id=org_id, transmission_id=transmission_id, receipt_ref=body.receipt_ref, by_user_id=ctx["user"]["id"], note=body.note)
    if not out:
        raise UserError("admin.transmission.tx_not_found")
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="filing.transmission_receipt", target_type="filing_transmission", target_id=transmission_id,
                detail={"receipt_ref": body.receipt_ref})
    session.commit()
    return out


class CredentialsBody(BaseModel):
    values: dict


@router.get("/channels/{channel_id}/credentials", summary="Which credentials this channel needs and which are set (values never returned)")
def channel_credentials(channel_id: str, session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    from services.supervision.mandates import registry
    from services.transmission.adapters import credentials_status
    from services.transmission.service import _org_channel_settings
    ch = registry()["channels"].get(channel_id)
    if not ch:
        raise UserError("admin.transmission.unknown_channel")
    return {"channel_id": channel_id, "label": ch["label"], **credentials_status(channel_id, ch, _org_channel_settings(session, ctx["org"]["org_id"]).get(channel_id))}


@router.put("/channels/{channel_id}/credentials", summary="Set this organisation's credentials for a channel (encrypted at rest; org admin)")
def set_credentials(channel_id: str, body: CredentialsBody, session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    from api.services.rbac import write_audit
    from services.transmission.service import set_channel_credentials
    out = set_channel_credentials(session, org_id=ctx["org"]["org_id"], channel_id=channel_id, values=body.values,
                                  by_user_id=ctx["user"]["id"])     # an unknown channel or credential: catalogue errors
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"], action="channel.credentials_updated", target_type="channel", target_id=channel_id,
                detail={"keys": list(body.values.keys())})
    session.commit()
    return out
