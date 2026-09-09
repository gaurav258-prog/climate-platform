"""The supervised entity's side of the regulator portal: who supervises me, and whether I have opened my
individual sites to them. Regional aggregates (NUTS-3) flow to the supervisor regardless — that is what filings
carry; SITE-level access is the entity's own decision, granted/revoked by an org admin, audited on both sides."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
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


# ── Regulatory attributes — what the criteria of a mandate read; the entity states them, the supervisor may ask ──
class AttributeSet(BaseModel):
    attributes: dict
    as_of: Optional[str] = None


@router.get("/regulatory-attributes", summary="My organisation's regulatory attributes (what mandate criteria read) and the registry's definitions")
def my_attributes(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.supervision.mandates import entity_attributes, registry
    return {"attributes": entity_attributes(session, ctx["org"]["org_id"]), "definitions": registry()["attributes"],
            "can_edit": "admin.users.manage" in (ctx.get("permissions") or [])}


@router.put("/regulatory-attributes", summary="Set my organisation's regulatory attributes (org admin; audited)")
def set_attributes(body: AttributeSet, session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    from services.supervision.mandates import registry, set_attribute
    org_id = ctx["org"]["org_id"]
    defs = registry()["attributes"]
    for k, v in body.attributes.items():
        if k not in defs or defs[k].get("source", "").startswith("organizations."):
            raise HTTPException(status_code=422, detail={"error": "invalid", "message": f"{k} is not an attribute you set here."})
        if v is None or v == "":
            session.execute(text("DELETE FROM org_regulatory_attribute WHERE org_id = CAST(:o AS uuid) AND attribute = :a"), {"o": org_id, "a": k})
            continue
        try:
            set_attribute(session, org_id, k, v, source="entity", by_user_id=ctx["user"]["id"], as_of=body.as_of)
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail={"error": "invalid", "message": f"{defs[k]['label']}: value not understood."})
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="regulatory_attributes.updated", target_type="organization",
                target_id=org_id, detail={"attributes": list(body.attributes.keys()), "as_of": body.as_of})
    # with the attributes known, deadlines each supervisor has already published can now apply to this entity
    from services.supervision.deadlines import apply_published
    for reg in session.execute(text("SELECT regulator_org_id::text FROM supervision_scope WHERE supervised_org_id = CAST(:o AS uuid) AND active"), {"o": org_id}).scalars().all():
        apply_published(session, reg, None)
    session.commit()
    from services.supervision.mandates import entity_attributes
    return {"attributes": entity_attributes(session, org_id)}


# ── Submitting the required template to a supervisor (portal or API; tenants and respondents alike) ─────────
def _can_submit(ctx: dict) -> None:
    if not ({"reports.publish", "respondent.portal"} & set(ctx.get("permissions") or [])):
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Submitting to a supervisor needs the release permission or the supervisory portal role."})


@router.get("/{supervision_id}/submission-spec", summary="The template this supervisor expects from us, and its fields")
def submission_spec_view(supervision_id: str, session: DbSession, ctx: CurrentUser):
    from services.supervision.respondents import submission_spec
    from services.supervision.trend import list_submissions
    spec = submission_spec(session, ctx["org"]["org_id"], supervision_id)
    if spec is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such supervisor for your organisation."})
    on_file = []
    if spec.get("available"):
        on_file = [{k: s[k] for k in ("period_label", "created_at", "n_cells", "source_file")} | {"basis": s.get("basis")}
                   for s in list_submissions(session, spec["regulator_org_id"], ctx["org"]["org_id"], spec["framework"], spec["template"])]
    return {**spec, "on_file": on_file}


@router.post("/{supervision_id}/submissions/validate", summary="Dry run: parse the template, suggest or apply a column mapping — saves nothing")
async def submission_validate(supervision_id: str, session: DbSession, ctx: CurrentUser, file: UploadFile = File(...), mapping: Optional[str] = Form(None)):
    import json as _json

    from services.ingest.upload_validation import parse_table
    from services.supervision.intake import map_rows, suggest_mapping
    from services.supervision.respondents import submission_spec
    _can_submit(ctx)
    spec = submission_spec(session, ctx["org"]["org_id"], supervision_id)
    if not spec or not spec.get("available"):
        raise HTTPException(status_code=422, detail={"error": "no_spec", "message": (spec or {}).get("reason") or "No supervisor found."})
    raw = await file.read()
    try:
        cols = [str(c) for c in parse_table(raw, file.filename).columns]
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "unreadable", "message": "The file could not be read. Please upload a valid CSV or Excel file."}) from e
    m = _json.loads(mapping) if mapping else suggest_mapping(cols, spec["fields"])
    rep = map_rows(raw, file.filename, spec["fields"], m)
    rep.pop("rows", None)
    return {"fields": spec["fields"], "mapping": m, **rep}


@router.post("/{supervision_id}/submissions", summary="Submit the template to this supervisor (audited on both sides)")
async def submission_submit(supervision_id: str, session: DbSession, ctx: CurrentUser, file: UploadFile = File(...), mapping: str = Form(...),
                            period_label: str = Form(...), basis: Optional[str] = Form(None)):
    import json as _json

    from services.supervision.respondents import submit_template
    _can_submit(ctx)
    org_id = ctx["org"]["org_id"]
    raw = await file.read()
    try:
        out = submit_template(session, supervised_org_id=org_id, supervision_id=supervision_id, raw=raw, filename=file.filename, mapping=_json.loads(mapping),
                              period_label=period_label, basis=_json.loads(basis) if basis else {}, user_id=ctx["user"]["id"],
                              channel="entity_portal")
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"error": "invalid", "message": str(e)})
    if not out["accepted"]:
        raise HTTPException(status_code=422, detail={"error": "invalid_file", "message": "Please correct the column mapping and flagged rows before submitting.", **out["report"]})
    reg = session.execute(text("SELECT regulator_org_id::text FROM supervision_scope WHERE supervision_id = CAST(:s AS uuid)"), {"s": supervision_id}).scalar()
    for audited in (org_id, reg):
        write_audit(session, org_id=audited, actor_user_id=ctx["user"]["id"], action="supervision.template_submitted", target_type="organization", target_id=org_id,
                    detail={"regulator_org_id": reg, "supervised_org_id": org_id, **out["result"], "channel": "entity_portal"})
    session.commit()
    return out
