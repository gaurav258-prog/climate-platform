"""Regulatory tasks — the Kanban board API. Reuses reports.view (see) / approvals.create (act)."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import DbSession, require_permission
import services.governance.tasks as T

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


class SpinTask(BaseModel):
    filing_id: str
    rule: str
    message: str = Field(..., max_length=300)
    severity: str
    assignee_user_id: Optional[str] = None


@router.get("/kri", summary="Key Regulatory Indicator dashboard for a framework")
def kri(framework: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.kri import kri as _kri
    return _kri(session, ctx["org"]["org_id"], framework)


@router.get("/kri/hazard", summary="The entities contributing a hazard's exposure (drill-down)")
def kri_hazard(framework: str, hazard: str, session: DbSession,
               ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.kri import kri_hazard as _kh
    return _kh(session, ctx["org"]["org_id"], framework, hazard)


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
        return T.comment(session, ctx["org"]["org_id"], task_id, ctx["user"]["id"], body.body)
    except T.TaskError as e:
        raise HTTPException(409, {"error": "task_error", "message": str(e)})


@router.post("/{task_id}/assign", summary="Assign (or unassign) a task")
def assign(task_id: str, body: TaskAssign, session: DbSession,
           ctx: dict = Depends(require_permission("approvals.create"))):
    try:
        return T.assign_task(session, ctx["org"]["org_id"], task_id, ctx["user"]["id"], body.assignee_user_id)
    except T.TaskError as e:
        raise HTTPException(409, {"error": "task_error", "message": str(e)})
