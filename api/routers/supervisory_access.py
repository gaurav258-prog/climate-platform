"""The supervised entity's side of the regulator portal: who supervises me, and whether I have opened my
individual sites to them. Regional aggregates (NUTS-3) flow to the supervisor regardless — that is what filings
carry; SITE-level access is the entity's own decision, granted/revoked by an org admin, audited on both sides.

What a screen reads here is in customer words (UI standard, 2026-10-16): explanations are message codes rendered by
core/messages.py, refusals are core/errors.py UserError codes (prefix supervision.respondent.), and an exception's own
text goes to the log only."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import text

from api.deps import CurrentUser, DbSession, attachment, require_permission
from api.services.rbac import write_audit
from core import messages
from core.errors import UserError

router = APIRouter(prefix="/v1/me/supervisors", tags=["Me"])
logger = logging.getLogger(__name__)


def _message(code: str, **params) -> dict:
    """A message for the screen: its label and the detail behind its ⓘ."""
    r = messages.render(code, **params)
    return {"code": code, "label": r["label"], "detail": r["detail"]}


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
    return {"supervisors": _rows(session, ctx["org"]["org_id"]), "about": _message("supervision.respondent.access")}


@router.post("/{supervision_id}/acknowledge", summary="Acknowledge that this authority supervises us (org admin)")
def acknowledge_supervisor(supervision_id: str, session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    from services.supervision.scope import acknowledge
    org_id = ctx["org"]["org_id"]
    if not acknowledge(session, org_id, supervision_id, ctx["user"]["id"]):
        raise UserError("supervision.respondent.nothing_to_acknowledge")
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
        raise UserError("error.not_found")
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
        raise UserError("error.not_found")
    req["can_set"] = [{"key": st, "label": status_label(st)} for st in allowed_next(req["kind"], "entity") if st != req["status"]]
    return req


@router.post("/requests/{request_id}/messages", summary="Respond to my supervisor and/or report progress")
def respond(request_id: str, body: EntityMessage, session: DbSession, ctx: dict = Depends(require_permission("reports.publish"))):
    from services.supervision.engagement import add_message, get, status_label
    req = get(session, request_id, supervised_org_id=ctx["org"]["org_id"])
    if not req:
        raise UserError("error.not_found")
    if not (body.body or "").strip() and not body.status_to:
        raise UserError("supervision.respondent.empty_reply")
    try:
        out = add_message(session, request_id, side="entity", author_id=ctx["user"]["id"], body=body.body, status_to=body.status_to)
    except PermissionError as e:
        logger.info(f"status change refused: {e}")
        raise UserError("supervision.respondent.status_not_allowed", kind=req["kind_label"].lower(),
                        from_status=status_label(req["status"]), to_status=status_label(body.status_to)) from e
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
            raise UserError("supervision.respondent.attribute_not_yours", attribute=(defs.get(k) or {}).get("label", "This value"))
        if v is None or v == "":
            session.execute(text("DELETE FROM org_regulatory_attribute WHERE org_id = CAST(:o AS uuid) AND attribute = :a"), {"o": org_id, "a": k})
            continue
        try:
            set_attribute(session, org_id, k, v, source="entity", by_user_id=ctx["user"]["id"], as_of=body.as_of)
        except (ValueError, TypeError) as e:
            raise UserError("supervision.respondent.attribute_value", attribute=defs[k]["label"]) from e
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
        raise UserError("supervision.respondent.cannot_submit")


def _spec(session, ctx: dict, supervision_id: str) -> dict:
    """The template this supervisor expects; refused in customer words when there is none."""
    from services.supervision.respondents import submission_spec
    spec = submission_spec(session, ctx["org"]["org_id"], supervision_id)
    if spec is None:
        raise UserError("error.not_found")
    if not spec.get("available"):
        raise UserError("supervision.respondent.no_template", regulator=spec["regulator"])
    return spec


@router.get("/{supervision_id}/submission-spec", summary="The template this supervisor expects from us, and its fields")
def submission_spec_view(supervision_id: str, session: DbSession, ctx: CurrentUser):
    from services.supervision.respondents import submission_spec
    from services.supervision.trend import list_submissions
    spec = submission_spec(session, ctx["org"]["org_id"], supervision_id)
    if spec is None:
        raise UserError("error.not_found")
    on_file = []
    if spec.get("available"):
        on_file = [{k: s[k] for k in ("period_label", "created_at", "n_cells", "source_file")} | {"basis": s.get("basis")}
                   for s in list_submissions(session, spec["regulator_org_id"], ctx["org"]["org_id"], spec["framework"], spec["template"])]
        level = spec.get("at_risk_level")
        spec["level_message"] = (_message("supervision.respondent.level_stated", level=f"{level:g}") if level is not None
                                 else _message("supervision.respondent.level_not_stated"))
    return {**spec, "on_file": on_file}


@router.post("/{supervision_id}/submissions/validate", summary="Dry run: parse the template, suggest or apply a column mapping — saves nothing")
async def submission_validate(supervision_id: str, session: DbSession, ctx: CurrentUser, file: UploadFile = File(...), mapping: Optional[str] = Form(None)):
    import json as _json

    from services.ingest.upload_validation import parse_table
    from services.supervision.intake import map_rows, suggest_mapping
    _can_submit(ctx)
    spec = _spec(session, ctx, supervision_id)
    raw = await file.read()
    try:
        cols = [str(c) for c in parse_table(raw, file.filename).columns]
    except ValueError as e:
        raise UserError("supervision.respondent.unreadable_file") from e
    m = _json.loads(mapping) if mapping else suggest_mapping(cols, spec["fields"])
    rep = map_rows(raw, file.filename, spec["fields"], m)
    rep.pop("rows", None)
    return {"fields": spec["fields"], "mapping": m, **rep}


@router.post("/{supervision_id}/submissions", summary="Submit the template to this supervisor (audited on both sides)")
async def submission_submit(supervision_id: str, session: DbSession, ctx: CurrentUser, file: UploadFile = File(...), mapping: str = Form(...),
                            period_label: str = Form(...), basis: Optional[str] = Form(None)):
    import json as _json

    from services.ingest.upload_validation import parse_table
    from services.supervision.levels import clean_basis
    from services.supervision.respondents import submit_template
    _can_submit(ctx)
    _spec(session, ctx, supervision_id)
    org_id = ctx["org"]["org_id"]
    stated = _json.loads(basis) if basis else {}
    try:
        clean_basis(stated)
    except ValueError as e:
        raise UserError("supervision.respondent.basis_invalid") from e
    raw = await file.read()
    try:
        parse_table(raw, file.filename)
    except ValueError as e:
        raise UserError("supervision.respondent.unreadable_file") from e
    try:
        out = submit_template(session, supervised_org_id=org_id, supervision_id=supervision_id, raw=raw, filename=file.filename, mapping=_json.loads(mapping),
                              period_label=period_label, basis=stated, user_id=ctx["user"]["id"], channel="entity_portal")
    except ValueError as e:
        logger.warning(f"submission refused: {e}")
        raise UserError("supervision.respondent.not_accepted") from e
    if not out["accepted"]:
        problems = _message("supervision.respondent.file_has_problems")
        raise HTTPException(status_code=422, detail={"error": problems["code"], "message": problems["label"], "detail": problems["detail"], **out["report"]})
    reg = session.execute(text("SELECT regulator_org_id::text FROM supervision_scope WHERE supervision_id = CAST(:s AS uuid)"), {"s": supervision_id}).scalar()
    for audited in (org_id, reg):
        write_audit(session, org_id=audited, actor_user_id=ctx["user"]["id"], action="supervision.template_submitted", target_type="organization", target_id=org_id,
                    detail={"regulator_org_id": reg, "supervised_org_id": org_id, **out["result"], "channel": "entity_portal"})
    session.commit()
    return out


@router.get("/requests/{request_id}/letter.pdf", summary="The formal letter my supervisor issued for this request")
def my_request_letter(request_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from fastapi.responses import Response

    from services.supervision.correspondence import letter
    L = letter(session, request_id, supervised_org_id=ctx["org"]["org_id"])
    if not L:
        raise UserError("error.not_found")
    return Response(content=L["pdf"], media_type="application/pdf", headers={"Content-Disposition": attachment(f"{L["reference"]}.pdf")})


@router.post("/requests/{request_id}/receipt", summary="Formally acknowledge receipt of the letter (once; audited on both sides)")
def acknowledge_request_receipt(request_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.supervision.correspondence import acknowledge_receipt
    from services.supervision.engagement import get
    org_id = ctx["org"]["org_id"]
    req = get(session, request_id, supervised_org_id=org_id)
    if not req:
        raise UserError("error.not_found")
    if not acknowledge_receipt(session, request_id, org_id, ctx["user"]["id"]):
        raise UserError("supervision.respondent.receipt_already")
    for audited in (org_id, req["regulator_org_id"]):
        write_audit(session, org_id=audited, actor_user_id=ctx["user"]["id"], action="supervisor.request.receipt", target_type="supervision_request",
                    target_id=request_id, detail={"reference": req.get("reference"), "supervised_org_id": org_id, "regulator_org_id": req["regulator_org_id"]})
    session.commit()
    return get(session, request_id, supervised_org_id=org_id)


@router.get("/mandates", summary="What applies to my organisation and why — every mandate for my sector judged against my attributes, with the criteria trace")
def my_mandates(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.supervision.mandates import applicability_for_entity
    return applicability_for_entity(session, ctx["org"]["org_id"])
