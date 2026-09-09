"""Reporting control register — view, test on demand, history, owners, export."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from api.deps import CurrentUser, DbSession, require_permission
from services.governance import controls as C

router = APIRouter(prefix="/v1/controls", tags=["Governance"])


def _regulated(ctx: dict) -> dict:
    if (ctx.get("org") or {}).get("type") == "regulator":
        raise HTTPException(status_code=404, detail={"error": "not_applicable", "message": "A supervisory body has no reporting control register."})
    return ctx


def _reader(ctx: CurrentUser) -> dict:
    """Read access: the operators (ops.oversee) and the auditor (admin.audit.view)."""
    if not ({"ops.oversee", "admin.audit.view"} & set(ctx["permissions"])):
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Missing permission: ops.oversee or admin.audit.view"})
    return ctx


@router.get("", summary="The reporting control register: every control, its owner, last outcome and pass rate")
def get_register(session: DbSession, ctx: dict = Depends(_reader), window_days: int = 90):
    _regulated(ctx)
    v = C.view(session, ctx["org"]["org_id"], window_days=max(7, min(window_days, 365)))
    v["can_manage"] = "ops.oversee" in ctx["permissions"]
    return v


@router.get("/people", summary="Active people in the organisation who can own a control (names only)")
def people(session: DbSession, ctx: dict = Depends(require_permission("ops.oversee"))):
    from sqlalchemy import text
    rows = session.execute(text("SELECT user_id::text AS user_id, full_name FROM users WHERE org_id = CAST(:o AS uuid) AND status = 'active' ORDER BY full_name"), {"o": ctx["org"]["org_id"]}).mappings().all()
    return {"people": [dict(r) for r in rows]}


@router.post("/test", summary="Test every control now and record the outcomes")
def test_now(session: DbSession, ctx: dict = Depends(require_permission("ops.oversee"))):
    _regulated(ctx)
    out = C.test_all(session, org_id=ctx["org"]["org_id"], org_type=ctx["org"].get("type"), actor_user_id=ctx["user"]["id"], trigger="manual")
    session.commit()
    return out


@router.get("/register.csv", summary="Export the register with outcomes (for the auditor or the GRC suite)")
def export_csv(session: DbSession, ctx: dict = Depends(_reader)):
    _regulated(ctx)
    v = C.view(session, ctx["org"]["org_id"])
    return Response(content=C.register_csv(v), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="reporting-control-register.csv"'})


@router.get("/{control_id}/history", summary="Every recorded test of one control")
def control_history(control_id: str, session: DbSession, ctx: dict = Depends(_reader)):
    _regulated(ctx)
    if not C.control(control_id):
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such control."})
    return {"control": C.control(control_id), "tests": C.history(session, ctx["org"]["org_id"], control_id)}


class Owner(BaseModel):
    owner_user_id: Optional[str] = None
    review_by: Optional[date] = None
    note: Optional[str] = None


@router.put("/{control_id}/owner", summary="Set the control's owner and review date")
def put_owner(control_id: str, body: Owner, session: DbSession, ctx: dict = Depends(require_permission("ops.oversee"))):
    _regulated(ctx)
    try:
        C.set_owner(session, org_id=ctx["org"]["org_id"], control_id=control_id, owner_user_id=body.owner_user_id, review_by=body.review_by, note=body.note, actor_user_id=ctx["user"]["id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"error": "invalid", "message": str(e)})
    session.commit()
    return {"ok": True}
