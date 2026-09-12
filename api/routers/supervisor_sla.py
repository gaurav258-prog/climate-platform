"""Regulator portal — engagement SLA and the obligations calendar per authority (read-only).

Same prefix and the same access gate as api.routers.supervisor (require_supervisor: regulator organisation +
supervisor.population.view); the SLA additionally needs the engagement permission the requests list needs.
Separate module so the supervisor router does not grow further; paths avoid the `/requests/{request_id}`
catch-all in that router (registered first) by living under `/engagement` and `/obligations`.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException

from api.deps import DbSession
from api.routers.supervisor import Supervisor, _config, _supervised

router = APIRouter(prefix="/v1/supervisor", tags=["Regulator portal"])


@router.get("/engagement/sla", summary="Requests & findings SLA per authority: time to acknowledge / respond / close, overdue ageing")
def engagement_sla(session: DbSession, ctx: Supervisor):
    from services.supervision.sla import sla_view
    if not ({"supervisor.requests.manage", "supervisor.findings.manage"} & set(ctx.get("permissions") or [])):
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Missing permission supervisor.requests.manage."})
    ents = _supervised(session, ctx)
    return sla_view(session, ctx["org"]["org_id"], [e["org_id"] for e in ents])


@router.get("/obligations/calendar", summary="Obligations calendar per authority: which deliverables are due to which authority, by when, and for which entities")
def obligations_calendar(session: DbSession, ctx: Supervisor, period_label: Optional[str] = None):
    from services.supervision.sla import authority_calendar
    reg = ctx["org"]["org_id"]
    pl = period_label or f"FY{date.today().year - 1}"
    if not pl.startswith("FY") or not pl[2:].isdigit():
        raise HTTPException(status_code=422, detail={"error": "invalid", "message": "period_label must look like FY2025."})
    return authority_calendar(session, reg, _config(session, reg), pl)
