"""Regulatory tasks — the Kanban board API. Reuses reports.view (see) / approvals.create (act)."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import text

import services.governance.tasks as T
from api.deps import DbSession, require_permission

router = APIRouter(prefix="/v1/reg-tasks", tags=["Regulatory tasks"])


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    description: Optional[str] = Field(None, max_length=4000)
    criticality: str = "normal"
    assignee_user_id: Optional[str] = None
    filing_id: Optional[str] = None
    due_date: Optional[str] = None
    depends_on: Optional[List[str]] = None


class TaskMove(BaseModel):
    status: str
    attestations: Optional[List[str]] = None  # the stage-gate checklist the mover confirmed (gated forward moves)


class TaskAssign(BaseModel):
    assignee_user_id: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=300)
    description: Optional[str] = Field(None, max_length=4000)
    criticality: Optional[str] = None
    due_date: Optional[str] = None
    clear_due: bool = False


class TaskComment(BaseModel):
    body: str = Field(..., min_length=1, max_length=2000)
    mentions: Optional[List[str]] = None  # user_ids the @mention picker resolved in the comment


class SpinTask(BaseModel):
    filing_id: str
    rule: str
    message: str = Field(..., max_length=300)
    severity: str
    assignee_user_id: Optional[str] = None


@router.get("/oversight", summary="Supervisor's-eye rollup — every filing's status, coverage, KRI breaches, readiness & exceptions")
def oversight(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.oversight import supervisor_view
    return supervisor_view(session, ctx["org"]["org_id"], ctx["org"].get("type"))


@router.get("/kri/frameworks", summary="The KRI frameworks this org can report on (for the picker)")
def kri_frameworks(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.kri import kri_frameworks as _kf
    return {"frameworks": _kf(ctx["org"].get("type"))}


@router.get("/kri", summary="Key Regulatory Indicator dashboard for a framework")
def kri(framework: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.kri import kri as _kri
    data = _kri(session, ctx["org"]["org_id"], framework)
    # detection lag: record what we observe now so breach onset is a real, persisted timestamp (best-effort)
    try:
        from services.governance import kri_monitor
        kri_monitor.observe(session, ctx["org"]["org_id"], framework, data)
    except Exception:
        pass
    return data


@router.get("/kri/detection-lag", summary="How long each KRI sat in breach before it was acted on")
def kri_detection_lag(session: DbSession, framework: Optional[str] = None,
                      ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance import kri_monitor
    return kri_monitor.detection_lag(session, ctx["org"]["org_id"], framework)


@router.get("/kri/detail", summary="Drill behind one KRI — methodology, trend & composition")
def kri_detail(framework: str, kri: str, session: DbSession,
               ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.kri import kri_detail as _kd
    return _kd(session, ctx["org"]["org_id"], framework, kri)


@router.get("/kri/hazard", summary="The entities contributing a hazard's exposure (drill-down)")
def kri_hazard(framework: str, hazard: str, session: DbSession,
               ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.kri import kri_hazard as _kh
    return _kh(session, ctx["org"]["org_id"], framework, hazard)


@router.get("/kri/drivers", summary="Individual exposures behind a KRI, optionally scoped to one segment")
def kri_drivers(framework: str, kri: str, session: DbSession,
                seg_type: Optional[str] = None, seg_value: Optional[str] = None,
                ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.kri import _kri_drivers
    return _kri_drivers(session, ctx["org"]["org_id"], framework, kri, seg_type, seg_value) \
        or {"unit": "eur", "total_count": 0, "items": []}


@router.get("/calendar", summary="Regulatory calendar — filing deadlines + task due-dates")
def calendar(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.reg_calendar import calendar as _cal
    return _cal(session, ctx["org"]["org_id"], ctx["org"]["type"])


@router.get("/exceptions", summary="Control Tower — every open exception across all filings")
def exceptions(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.exception_monitor import exceptions as _exc
    return _exc(session, ctx["org"]["org_id"])


@router.post("/exceptions/spin-task", status_code=201, summary="Turn an exception into a task")
def spin_task(body: SpinTask, session: DbSession, ctx: dict = Depends(require_permission("approvals.create"))):
    from services.governance.exception_monitor import spin_task as _spin
    try:
        return _spin(session, ctx["org"]["org_id"], ctx["user"]["id"], filing_id=body.filing_id,
                     rule=body.rule, message=body.message, severity=body.severity,
                     assignee_user_id=body.assignee_user_id)
    except T.TaskError as e:
        raise HTTPException(409, {"error": "task_error", "message": str(e)})


class KriTask(BaseModel):
    framework: str = Field(..., max_length=60)
    key:       str = Field(..., max_length=80)
    label:     str = Field(..., max_length=200)
    detail:    Optional[str] = Field(None, max_length=300)   # e.g. "53.7% · warn ≥15% · breach ≥30%"


@router.post("/kri/spin-task", status_code=201, summary="Raise a task to remediate a KRI breach")
def kri_spin_task(body: KriTask, session: DbSession, ctx: dict = Depends(require_permission("approvals.create"))):
    title = f"KRI breach — {body.label}"[:300]
    desc = (f"Indicator '{body.label}' is outside appetite"
            + (f": {body.detail}" if body.detail else "") + ".\n"
            + f"Framework: {body.framework}. Raised from the KRI dashboard — review and remediate.")
    try:
        # source_ref de-dupes: a live task for this indicator returns the existing one, no pile-up
        task = T.create_task(session, ctx["org"]["org_id"], ctx["user"]["id"], title=title, description=desc,
                             criticality="high", source="kri", source_ref=f"{body.framework}:{body.key}")
    except T.TaskError as e:
        raise HTTPException(409, {"error": "task_error", "message": str(e)})
    # raising the remediation task IS the human acknowledgement — stamp the open breach episode for detection lag
    try:
        from services.governance import kri_monitor
        kri_monitor.acknowledge(session, ctx["org"]["org_id"], body.framework, body.key, ctx["user"]["id"])
    except Exception:
        pass
    return task


@router.get("/board", summary="The Kanban board — tasks grouped into columns")
def board(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return T.board(session, ctx["org"]["org_id"])


@router.get("/members", summary="Users a task can be assigned to")
def members(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    rows = session.execute(text("""
        SELECT user_id, email, full_name FROM users WHERE org_id = :o AND status = 'active' ORDER BY email
    """), {"o": ctx["org"]["org_id"]}).mappings().all()
    return [{"user_id": str(r["user_id"]), "email": r["email"], "name": r["full_name"]} for r in rows]


@router.post("", status_code=201, summary="Create a task")
def create(body: TaskCreate, session: DbSession, ctx: dict = Depends(require_permission("approvals.create"))):
    try:
        return T.create_task(session, ctx["org"]["org_id"], ctx["user"]["id"], title=body.title,
                             description=body.description, criticality=body.criticality,
                             assignee_user_id=body.assignee_user_id, filing_id=body.filing_id,
                             due_date=body.due_date, depends_on=body.depends_on)
    except T.TaskError as e:
        raise HTTPException(409, {"error": "task_error", "message": str(e)})


@router.get("/mentions", summary="My unread @mentions across the board")
def mentions(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return T.my_mentions(session, ctx["org"]["org_id"], ctx["user"]["id"])


@router.get("/{task_id}", summary="One task with its activity")
def get(task_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    t = T.get_task(session, ctx["org"]["org_id"], task_id)
    if not t:
        raise HTTPException(404, {"error": "not_found", "message": "Task not found."})
    return t


@router.post("/{task_id}/move", summary="Move a task to another column")
def move(task_id: str, body: TaskMove, session: DbSession,
         ctx: dict = Depends(require_permission("approvals.create"))):
    try:
        return T.move_task(session, ctx["org"]["org_id"], task_id, ctx["user"]["id"], body.status, body.attestations)
    except T.TaskError as e:
        raise HTTPException(409, {"error": "task_error", "message": str(e)})


@router.patch("/{task_id}", summary="Edit a task's fields")
def update(task_id: str, body: TaskUpdate, session: DbSession,
           ctx: dict = Depends(require_permission("approvals.create"))):
    try:
        return T.update_task(session, ctx["org"]["org_id"], task_id, ctx["user"]["id"], title=body.title,
                             description=body.description, criticality=body.criticality,
                             due_date=body.due_date, clear_due=body.clear_due)
    except T.TaskError as e:
        raise HTTPException(409, {"error": "task_error", "message": str(e)})


@router.post("/{task_id}/comment", summary="Add a comment to a task")
def comment(task_id: str, body: TaskComment, session: DbSession,
            ctx: dict = Depends(require_permission("approvals.create"))):
    try:
        return T.comment(session, ctx["org"]["org_id"], task_id, ctx["user"]["id"], body.body, body.mentions)
    except T.TaskError as e:
        raise HTTPException(409, {"error": "task_error", "message": str(e)})


@router.post("/{task_id}/assign", summary="Assign (or unassign) a task")
def assign(task_id: str, body: TaskAssign, session: DbSession,
           ctx: dict = Depends(require_permission("approvals.create"))):
    try:
        return T.assign_task(session, ctx["org"]["org_id"], task_id, ctx["user"]["id"], body.assignee_user_id)
    except T.TaskError as e:
        raise HTTPException(409, {"error": "task_error", "message": str(e)})


# ── attachments ──────────────────────────────────────────────────────────────────────────────────────────
@router.post("/{task_id}/attachments", status_code=201, summary="Attach a file to a task")
async def upload_attachment(task_id: str, session: DbSession, file: UploadFile = File(...),
                            ctx: dict = Depends(require_permission("approvals.create"))):
    data = await file.read()
    try:
        return T.add_attachment(session, ctx["org"]["org_id"], task_id, ctx["user"]["id"],
                                filename=file.filename or "file", content_type=file.content_type, data=data)
    except T.TaskError as e:
        raise HTTPException(409, {"error": "task_error", "message": str(e)})


@router.get("/{task_id}/attachments", summary="List a task's attachments")
def attachments(task_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return T.list_attachments(session, ctx["org"]["org_id"], task_id)


@router.get("/{task_id}/attachments/{attachment_id}", summary="Download an attachment")
def download_attachment(task_id: str, attachment_id: str, session: DbSession,
                        ctx: dict = Depends(require_permission("reports.view"))):
    a = T.get_attachment(session, ctx["org"]["org_id"], task_id, attachment_id)
    if not a:
        raise HTTPException(404, {"error": "not_found", "message": "Attachment not found."})
    # ASCII-safe Content-Disposition (RFC 5987 filename* for the real name)
    from urllib.parse import quote
    disp = f"attachment; filename*=UTF-8''{quote(a['filename'])}"
    return Response(content=a["data"], media_type=a["content_type"], headers={"Content-Disposition": disp})


@router.delete("/{task_id}/attachments/{attachment_id}", status_code=204, summary="Remove an attachment")
def remove_attachment(task_id: str, attachment_id: str, session: DbSession,
                      ctx: dict = Depends(require_permission("approvals.create"))):
    T.delete_attachment(session, ctx["org"]["org_id"], task_id, attachment_id, ctx["user"]["id"])
    return Response(status_code=204)


@router.post("/{task_id}/seen", status_code=204, summary="Mark my @mentions on a task as read")
def seen(task_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    T.mark_mentions_seen(session, ctx["org"]["org_id"], task_id, ctx["user"]["id"])
    return Response(status_code=204)
