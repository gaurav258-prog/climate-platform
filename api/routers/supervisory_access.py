"""The supervised entity's side of the regulator portal: who supervises me, and whether I have opened my
individual sites to them. Regional aggregates (NUTS-3) flow to the supervisor regardless — that is what filings
carry; SITE-level access is the entity's own decision, granted/revoked by an org admin, audited on both sides."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from api.deps import CurrentUser, DbSession, require_permission
from api.services.rbac import write_audit

router = APIRouter(prefix="/v1/me/supervisors", tags=["Me"])


def _rows(session, org_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT ss.supervision_id::text AS supervision_id, o.org_id::text AS regulator_org_id, o.name AS regulator,
               ss.jurisdiction, ss.site_access_granted_at, ss.site_access_revoked_at, ss.created_at, ss.acknowledged_at,
               (ss.site_access_granted_at IS NOT NULL AND ss.site_access_revoked_at IS NULL) AS site_access
        FROM supervision_scope ss JOIN organizations o ON o.org_id = ss.regulator_org_id
        WHERE ss.supervised_org_id = CAST(:o AS uuid) AND ss.active ORDER BY o.name
    """), {"o": org_id}).mappings().all()
    return [dict(r) | {"site_access_granted_at": r["site_access_granted_at"].isoformat() if r["site_access_granted_at"] else None,
                       "site_access_revoked_at": r["site_access_revoked_at"].isoformat() if r["site_access_revoked_at"] else None,
                       "since": r["created_at"].isoformat() if r["created_at"] else None,
                       "acknowledged_at": r["acknowledged_at"].isoformat() if r["acknowledged_at"] else None}
            for r in rows]


@router.get("", summary="My supervisors and what each may see")
def my_supervisors(session: DbSession, ctx: CurrentUser):
    return {"supervisors": _rows(session, ctx["org"]["org_id"]),
            "note": "Regional aggregates (NUTS-3), the unit used in filings, are visible to your supervisor by default. "
                    "Individual site locations are shown only while you grant site-level access here."}


@router.post("/{supervision_id}/acknowledge", summary="Acknowledge that this authority supervises us (org admin)")
def acknowledge_supervisor(supervision_id: str, session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    from services.supervision.scope import acknowledge
    org_id = ctx["org"]["org_id"]
    if not acknowledge(session, org_id, supervision_id, ctx["user"]["id"]):
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such supervisor awaiting acknowledgement."})
    reg = session.execute(text("SELECT regulator_org_id::text FROM supervision_scope WHERE supervision_id = CAST(:s AS uuid)"), {"s": supervision_id}).scalar()
    for audited in (org_id, reg):
        write_audit(session, org_id=audited, actor_user_id=ctx["user"]["id"], action="supervision.acknowledged",
                    target_type="supervision_scope", target_id=supervision_id, detail={"supervised_org_id": org_id, "regulator_org_id": reg})
    session.commit()
    return {"ok": True, "supervisors": _rows(session, org_id)}


class SiteAccess(BaseModel):
    granted: bool


@router.post("/{supervision_id}/site-access", summary="Grant or revoke site-level access for one supervisor (org admin)")
def set_site_access(supervision_id: str, body: SiteAccess, session: DbSession,
                    ctx: dict = Depends(require_permission("admin.users.manage"))):
    org_id = ctx["org"]["org_id"]
    row = session.execute(text("""
        SELECT supervision_id, regulator_org_id::text AS reg FROM supervision_scope
        WHERE supervision_id = CAST(:s AS uuid) AND supervised_org_id = CAST(:o AS uuid) AND active
    """), {"s": supervision_id, "o": org_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such supervisor for your organization."})
    if body.granted:
        session.execute(text("""UPDATE supervision_scope SET site_access_granted_at = now(), site_access_granted_by = CAST(:u AS uuid),
                                site_access_revoked_at = NULL WHERE supervision_id = CAST(:s AS uuid)"""),
                        {"u": ctx["user"]["id"], "s": supervision_id})
    else:
        session.execute(text("UPDATE supervision_scope SET site_access_revoked_at = now() WHERE supervision_id = CAST(:s AS uuid)"),
                        {"s": supervision_id})
    action = "supervisor.site_access.granted" if body.granted else "supervisor.site_access.revoked"
    for audited_org in (org_id, row["reg"]):   # both sides see the change in their own audit log
        write_audit(session, org_id=audited_org, actor_user_id=ctx["user"]["id"], action=action,
                    target_type="supervision_scope", target_id=supervision_id,
                    detail={"supervised_org_id": org_id, "regulator_org_id": row["reg"]})
    session.commit()
    return {"ok": True, "supervisors": _rows(session, org_id)}


# ── Requests from my supervisor: read for anyone with reports.view, respond with reports.publish ────────────
class EntityMessage(BaseModel):
    body: Optional[str] = None
    status_to: Optional[str] = None


@router.get("/requests", summary="Requests and findings my supervisors have raised with us")
def my_requests(session: DbSession, ctx: dict = Depends(require_permission("reports.view")), status: Optional[str] = None):
    from services.supervision.engagement import kinds, list_requests, status_label
    rows = list_requests(session, supervised_org_id=ctx["org"]["org_id"], status=status)
    return {"requests": rows, "can_respond": "reports.publish" in (ctx.get("permissions") or []),
            "kinds": {k: {"label": v["label"], "entity_sets": [{"key": st, "label": status_label(st)} for st in v["entity_sets"]]}
                      for k, v in kinds().items()},
            "summary": {"open": sum(1 for r in rows if r["status"] != "closed"), "overdue": sum(1 for r in rows if r["overdue"])}}


@router.get("/requests/{request_id}", summary="One request from my supervisor with its thread")
def my_request(request_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.supervision.engagement import allowed_next, get, status_label
    req = get(session, request_id, supervised_org_id=ctx["org"]["org_id"])
    if not req:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such request for your organisation."})
    req["can_set"] = [{"key": st, "label": status_label(st)} for st in allowed_next(req["kind"], "entity") if st != req["status"]]
    return req


@router.post("/requests/{request_id}/messages", summary="Respond to my supervisor and/or report progress")
def respond(request_id: str, body: EntityMessage, session: DbSession, ctx: dict = Depends(require_permission("reports.publish"))):
    from services.supervision.engagement import add_message, get
    req = get(session, request_id, supervised_org_id=ctx["org"]["org_id"])
    if not req:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such request for your organisation."})
    if not (body.body or "").strip() and not body.status_to:
        raise HTTPException(status_code=422, detail={"error": "invalid", "message": "Write a message or choose a status."})
    try:
        out = add_message(session, request_id, side="entity", author_id=ctx["user"]["id"], body=body.body, status_to=body.status_to)
    except PermissionError as e:
        raise HTTPException(status_code=422, detail={"error": "invalid", "message": str(e)})
    action = "supervisor.request.status" if body.status_to else "supervisor.request.message"
    for audited in (ctx["org"]["org_id"], req["regulator_org_id"]):
        write_audit(session, org_id=audited, actor_user_id=ctx["user"]["id"], action=action, target_type="supervision_request",
                    target_id=request_id, detail={"status_to": body.status_to, "side": "entity", "supervised_org_id": ctx["org"]["org_id"]})
    session.commit()
    return out
