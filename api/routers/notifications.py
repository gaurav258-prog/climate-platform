"""Regulatory-notification clock — raise a notifiable breach/incident, run its statutory countdown, and record
what was sent. The 'notify within N hours' obligation the calendar can't express."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import DbSession, require_permission
import services.governance.notification_clock as N

router = APIRouter(prefix="/v1/notifications", tags=["Regulatory notifications"])


class RaiseBody(BaseModel):
    title: str = Field(..., max_length=240)
    source_type: str = Field("manual", max_length=30)
    source_ref: Optional[str] = Field(None, max_length=160)
    category: str = Field("material_breach", max_length=40)
    severity: Optional[str] = Field(None, max_length=10)
    authority: Optional[str] = Field(None, max_length=120)
    arose_at_iso: Optional[str] = None
    window_hours: int = Field(N.DEFAULT_WINDOW_HOURS, ge=1, le=8760)
    assignee_user_id: Optional[str] = None


class RecordBody(BaseModel):
    notified_ref: Optional[str] = Field(None, max_length=160)
    notified_to: Optional[str] = Field(None, max_length=200)


class DismissBody(BaseModel):
    reason: str = Field(..., max_length=500)


@router.get("", summary="Open & recently-notified regulatory notifications, with live countdowns")
def list_notifications(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return N.open_events(session, ctx["org"]["org_id"])


@router.post("", status_code=201, summary="Flag a breach/incident as regulatorily notifiable (start the clock)")
def raise_notification(body: RaiseBody, session: DbSession, ctx: dict = Depends(require_permission("reports.publish"))):
    return N.raise_event(session, ctx["org"]["org_id"], title=body.title, source_type=body.source_type,
                         source_ref=body.source_ref, category=body.category, severity=body.severity,
                         authority=body.authority, arose_at_iso=body.arose_at_iso, window_hours=body.window_hours,
                         assignee_user_id=body.assignee_user_id, user_id=ctx["user"]["id"])


@router.post("/{event_id}/record", summary="Record the notification actually sent (reference, recipient, time)")
def record_notification(event_id: str, body: RecordBody, session: DbSession,
                        ctx: dict = Depends(require_permission("reports.publish"))):
    if not N.record(session, ctx["org"]["org_id"], event_id, notified_ref=body.notified_ref,
                    notified_to=body.notified_to, user_id=ctx["user"]["id"]):
        raise HTTPException(404, {"error": "not_found", "message": "Open notification not found."})
    return {"ok": True}


@router.post("/{event_id}/dismiss", summary="Dismiss a notifiable event (with a reason, audited)")
def dismiss_notification(event_id: str, body: DismissBody, session: DbSession,
                         ctx: dict = Depends(require_permission("reports.publish"))):
    if not N.dismiss(session, ctx["org"]["org_id"], event_id, reason=body.reason, user_id=ctx["user"]["id"]):
        raise HTTPException(404, {"error": "not_found", "message": "Open notification not found."})
    return {"ok": True}
