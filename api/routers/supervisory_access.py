"""The supervised entity's side of the regulator portal: who supervises me, and whether I have opened my
individual sites to them. Regional aggregates (NUTS-3) flow to the supervisor regardless — that is what filings
carry; SITE-level access is the entity's own decision, granted/revoked by an org admin, audited on both sides."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from api.deps import CurrentUser, DbSession, require_permission
from api.services.rbac import write_audit

router = APIRouter(prefix="/v1/me/supervisors", tags=["Me"])


def _rows(session, org_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT ss.supervision_id::text AS supervision_id, o.org_id::text AS regulator_org_id, o.name AS regulator,
               ss.jurisdiction, ss.site_access_granted_at, ss.site_access_revoked_at,
               (ss.site_access_granted_at IS NOT NULL AND ss.site_access_revoked_at IS NULL) AS site_access
        FROM supervision_scope ss JOIN organizations o ON o.org_id = ss.regulator_org_id
        WHERE ss.supervised_org_id = CAST(:o AS uuid) AND ss.active ORDER BY o.name
    """), {"o": org_id}).mappings().all()
    return [dict(r) | {"site_access_granted_at": r["site_access_granted_at"].isoformat() if r["site_access_granted_at"] else None,
                       "site_access_revoked_at": r["site_access_revoked_at"].isoformat() if r["site_access_revoked_at"] else None}
            for r in rows]


@router.get("", summary="My supervisors and what each may see")
def my_supervisors(session: DbSession, ctx: CurrentUser):
    return {"supervisors": _rows(session, ctx["org"]["org_id"]),
            "note": "Regional aggregates (NUTS-3) are visible to your supervisor by default — the unit filings use. "
                    "Individual site locations are shown only while you grant site-level access here."}


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
