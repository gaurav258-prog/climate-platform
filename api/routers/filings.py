"""Reporting cockpit — the regulatory filing register, lifecycle and obligations calendar.

The lifecycle maps onto existing permissions and machinery:
  - prepare / submit-for-review   → approvals.create (the maker)
  - withdraw (discard a draft)    → approvals.create (the maker; draft/returned only, reason required)
  - approve                       → done through /v1/approvals/{id}/decide (approvals.decide, checker ≠ maker)
  - attest                        → board.attest (the accountable person's personal certification — see below)
  - submit / accept               → reports.publish (transmitting to / recording acknowledgement from the regulator)
  - view                         → reports.view

Attestation identity (fixed 2026-09-23, an independent architecture review finding): attest() used to take
`attestor_name` as free text from the request body — anyone holding `reports.publish` could type any name in
and it would be recorded as having certified the filing. Attestation is personal accountability, not process
control (that's what 4-eyes approval already is), so it must be bound to a real, authenticated identity: the
name recorded is now always the CALLING user's own `full_name` on file, resolved server-side from their
session — never a client-supplied string — and attest sits behind its own permission (`board.attest`,
already in the tenant permission catalog but previously unused) rather than sharing `reports.publish` with
submit/accept, so a preparer with only publish rights cannot self-attest.

Nothing here re-freezes a report: generate wraps report_snapshots.create_snapshot, so the frozen bytes are
the same immutable, hashed, versioned record the assurance pack already verifies.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import DbSession, require_permission
from api.services.rbac import write_audit
from services.governance import filings as F

router = APIRouter(prefix="/v1", tags=["Reporting cockpit"])


class GenerateBody(BaseModel):
    framework: str = Field(..., min_length=1, max_length=60)
    note: Optional[str] = Field(None, max_length=500)
    # The confirm_token GET /filings/preflight?framework=... just returned — proves the caller actually saw
    # (and is confirming) the CURRENT data, not a stale bare `confirmed: true` (see filings._confirm_token).
    confirm_token: Optional[str] = Field(None, max_length=64)
    entity_id: Optional[str] = None   # scope to one reporting entity; None = whole org (the default)
    obligation_id: Optional[str] = None   # prepared for this obligation: its entity and period are enforced
    fund_id: Optional[str] = None   # a per-product report (SFDR Annexes II–V): the fund it discloses
    # intake phase 5: which values of the asset facts the engine reads, and per reported figure whose number is reported
    view: Literal["joint", "client", "tellumen"] = "joint"
    figure_sources: dict[str, Literal["client", "tellumen"]] = Field(default_factory=dict)


class QualitativePatch(BaseModel):
    values: dict[str, str]    # {'table1.a': 'authored text', ...}


@router.get("/filings/qualitative/p3esg", summary="Pillar 3 ESG qualitative tables (1-3) + authored text")
def get_p3esg_qualitative(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    import json as _json

    from services.governance.pillar3_qualitative import qualitative_structure
    row = session.execute(text("SELECT p3esg_narratives FROM organizations WHERE org_id = CAST(:o AS uuid)"),
                          {"o": ctx["org"]["org_id"]}).scalar()
    saved = (_json.loads(row) if isinstance(row, str) else row) or {}
    return qualitative_structure(saved)


@router.patch("/filings/qualitative/p3esg", summary="Author / save a Pillar 3 ESG qualitative disclosure row")
def set_p3esg_qualitative(body: QualitativePatch, session: DbSession,
                          ctx: dict = Depends(require_permission("approvals.create"))):
    import json as _json

    from services.governance.pillar3_qualitative import qualitative_structure, valid_keys
    unknown = sorted(set(body.values) - valid_keys())
    if unknown:
        raise HTTPException(422, {"error": "unknown_rows", "message": f"Not a row of the governing tables: {', '.join(unknown[:5])}"})
    row = session.execute(text("SELECT p3esg_narratives FROM organizations WHERE org_id = CAST(:o AS uuid)"),
                          {"o": ctx["org"]["org_id"]}).scalar()
    cur = (_json.loads(row) if isinstance(row, str) else row) or {}
    cur.update({k: v for k, v in body.values.items()})
    session.execute(text("UPDATE organizations SET p3esg_narratives = CAST(:n AS jsonb) WHERE org_id = CAST(:o AS uuid)"),
                    {"n": _json.dumps(cur), "o": ctx["org"]["org_id"]})
    session.commit()
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="p3esg.qualitative.author", target_type="organization", target_id=ctx["org"]["org_id"],
                detail={"rows": list(body.values.keys())})
    return qualitative_structure(cur)


class BasisPatch(BaseModel):
    scenario: Optional[str] = None
    horizon: Optional[str] = None
    materiality_threshold: Optional[int] = Field(None, ge=0, le=100)
    reporting_period_end: Optional[str] = None


class AttestBody(BaseModel):
    # No attestor_name field: the attestor is always the calling user's own authenticated identity (see
    # module docstring) — a client can never supply who is attesting, only what they certify.
    statement: str = Field(..., min_length=1, max_length=2000)


class SubmitBody(BaseModel):
    submission_ref: Optional[str] = Field(None, max_length=200)


class AcceptBody(BaseModel):
    ack_ref: Optional[str] = Field(None, max_length=200)


class RestateBody(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000)


class WithdrawBody(BaseModel):
    reason: str = Field(..., min_length=F.WITHDRAW_REASON_MIN, max_length=1000)


def _audit(session, ctx, action, filing_id, detail=None):
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action=action, target_type="filing", target_id=str(filing_id), detail=detail or {})


# ── read surfaces ───────────────────────────────────────────────────────

@router.get("/obligations", summary="Regulatory filing calendar — what's due, by when")
def obligations(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return {"obligations": F.list_obligations(session, ctx["org"]["org_id"], ctx["org"]["type"])}


@router.get("/filings/frameworks", summary="Frameworks this organisation can file")
def frameworks(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return {"frameworks": F.available_frameworks(ctx["org"]["type"])}


@router.get("/filings/requirements", summary="Every mandatory reporting requirement — regulation, cadence, links, last filed")
def reporting_requirements(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return {"requirements": F.reporting_requirements(session, ctx["org"]["org_id"], ctx["org"]["type"])}


@router.get("/filings/entities", summary="The reporting-entity hierarchy — file per entity or consolidate a group")
def filing_entities(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance import entities as E
    from services.governance.reporting_settings import get_settings
    org_id = ctx["org"]["org_id"]
    eff = E.effective_currencies(session, org_id)
    tree = [{**e, "effective_currency": eff.get(e["entity_id"], {}).get("currency"),
             "currency_inherited_from": eff.get(e["entity_id"], {}).get("inherited_from")} for e in E.entity_tree(session, org_id)]
    return {"entities": tree, "presentation_currency": get_settings(session, org_id)["presentation_currency"]}


class EntityCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    kind: str = Field("legal_entity", max_length=40)
    parent_entity_id: Optional[str] = None
    ownership_pct: float = Field(100.0, ge=0, le=100)
    consolidation_method: str = Field("full", max_length=20)
    # Required only when the method runs counter to the IFRS 10 control presumption from ownership_pct alone
    # (e.g. 'full' below 50% or 'proportional'/'equity' above 50%) — rejected by the service layer otherwise.
    consolidation_basis: Optional[str] = Field(None, max_length=2000)
    # None = use the CRR-safe default (True, except kind='branch' → False — see entities.create_entity).
    # Setting a waiver reason without also setting requires_solo_filing=False is rejected by the service layer.
    requires_solo_filing: Optional[bool] = None
    solo_waiver_reason: Optional[str] = Field(None, max_length=2000)
    functional_currency: Optional[str] = Field(None, max_length=3, description="ISO 4217; blank = inherit from the parent")
    lei: Optional[str] = Field(None, max_length=20, description="the entity's own LEI (ISO 17442) — identifies it in its filings")
    country: Optional[str] = Field(None, max_length=2, description="ISO 3166 country whose law governs its records; blank = the organisation's")


class EntityPatch(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    kind: Optional[str] = Field(None, max_length=40)
    parent_entity_id: Optional[str] = None
    set_parent: bool = False   # apply parent_entity_id (True lets you move a node to the top with null)
    ownership_pct: Optional[float] = Field(None, ge=0, le=100)
    consolidation_method: Optional[str] = Field(None, max_length=20)
    consolidation_basis: Optional[str] = Field(None, max_length=2000)
    set_consolidation_basis: bool = False   # apply consolidation_basis (True lets you clear it with null)
    requires_solo_filing: Optional[bool] = None
    solo_waiver_reason: Optional[str] = Field(None, max_length=2000)
    set_solo_waiver_reason: bool = False   # apply solo_waiver_reason (True lets you clear it with null)
    functional_currency: Optional[str] = Field(None, max_length=3)
    set_functional_currency: bool = False  # apply functional_currency (True with null = inherit from the parent)
    lei: Optional[str] = Field(None, max_length=20)
    set_lei: bool = False                  # apply lei (True with null = remove it)
    country: Optional[str] = Field(None, max_length=2)
    set_country: bool = False              # apply country (True with null = the organisation's)


@router.post("/filings/entities", status_code=201, summary="Add a reporting entity to the hierarchy")
def create_entity(body: EntityCreate, session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    from services.governance import entities as E
    try:
        e = E.create_entity(session, ctx["org"]["org_id"], name=body.name, kind=body.kind,
                            parent_entity_id=body.parent_entity_id, ownership_pct=body.ownership_pct,
                            consolidation_method=body.consolidation_method,
                            consolidation_basis=body.consolidation_basis,
                            requires_solo_filing=body.requires_solo_filing,
                            solo_waiver_reason=body.solo_waiver_reason, functional_currency=body.functional_currency,
                            lei=body.lei, country=body.country)
    except E.EntityError as ex:
        raise HTTPException(409, {"error": "entity_error", "message": str(ex)})
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"], action="entity.create",
                target_type="reporting_entity", target_id=e["entity_id"], detail={"name": body.name, "kind": body.kind})
    return e


@router.patch("/filings/entities/{entity_id}", summary="Edit a reporting entity (name / parent / ownership / method / solo-filing waiver)")
def update_entity(entity_id: str, body: EntityPatch, session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    from services.governance import entities as E
    kwargs: dict = {}
    if body.name is not None: kwargs["name"] = body.name
    if body.kind is not None: kwargs["kind"] = body.kind
    if body.ownership_pct is not None: kwargs["ownership_pct"] = body.ownership_pct
    if body.consolidation_method is not None: kwargs["consolidation_method"] = body.consolidation_method
    if body.set_consolidation_basis: kwargs["consolidation_basis"] = body.consolidation_basis
    if body.set_parent: kwargs["parent_entity_id"] = body.parent_entity_id
    if body.requires_solo_filing is not None: kwargs["requires_solo_filing"] = body.requires_solo_filing
    if body.set_solo_waiver_reason: kwargs["solo_waiver_reason"] = body.solo_waiver_reason
    if body.set_functional_currency: kwargs["functional_currency"] = body.functional_currency
    if body.set_lei: kwargs["lei"] = body.lei
    if body.set_country: kwargs["country"] = body.country
    try:
        e = E.update_entity(session, ctx["org"]["org_id"], entity_id, **kwargs)
    except E.EntityError as ex:
        raise HTTPException(409, {"error": "entity_error", "message": str(ex)})
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"], action="entity.update",
                target_type="reporting_entity", target_id=entity_id, detail=kwargs)
    return e


@router.delete("/filings/entities/{entity_id}", summary="Remove a reporting entity (its book falls back to whole-org)")
def delete_entity(entity_id: str, session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    from services.governance import entities as E
    try:
        E.delete_entity(session, ctx["org"]["org_id"], entity_id)
    except E.EntityError as ex:
        raise HTTPException(409, {"error": "entity_error", "message": str(ex)})
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"], action="entity.delete",
                target_type="reporting_entity", target_id=entity_id, detail={})
    return {"ok": True}


@router.get("/filings/{filing_id}/form", summary="The final form — the frozen disclosure as labelled datapoints")
def filing_form(filing_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    v = F.form_view(session, ctx["org"]["org_id"], filing_id)
    if not v:
        raise HTTPException(404, {"error": "not_found", "message": "Filing not found."})
    return v


class CellOverride(BaseModel):
    datapoint_key: str = Field(..., min_length=1, max_length=120)
    value: float
    reason: str = Field(..., min_length=1, max_length=500)


@router.post("/filings/{filing_id}/overrides", status_code=201, summary="Propose a manual override of one form cell (needs 4-eyes)")
def propose_override(filing_id: str, body: CellOverride, session: DbSession,
                     ctx: dict = Depends(require_permission("approvals.create"))):
    from services.governance import filing_overrides as O
    try:
        r = O.propose(session, ctx["org"]["org_id"], filing_id, ctx["user"]["id"],
                      datapoint_key=body.datapoint_key, value=body.value, reason=body.reason)
    except O.OverrideError as e:
        raise HTTPException(409, {"error": "override_error", "message": str(e)})
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"], action="filing.cell_override.propose",
                target_type="regulatory_filing", target_id=filing_id,
                detail={"datapoint_key": body.datapoint_key, "to": body.value, "reason": body.reason})
    return r


@router.get("/filings", summary="The filing register — every filing, newest first")
def list_filings(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return {"filings": F.list_filings(session, ctx["org"]["org_id"])}


@router.get("/filings/reporting-basis", summary="The org's reporting basis (scenario / horizon / materiality / period)")
def get_basis(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.reporting_settings import get_settings
    return get_settings(session, ctx["org"]["org_id"])


@router.patch("/filings/reporting-basis", summary="Set the reporting basis (audited; 4-eyes if the matrix requires it)")
def set_basis(body: BasisPatch, session: DbSession, ctx: dict = Depends(require_permission("reports.publish"))):
    from services.governance.config_governance import submit_or_apply_config
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    if not changes:
        raise HTTPException(422, {"error": "no_changes", "message": "Nothing to change."})
    return submit_or_apply_config(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                                  request_type="config.reporting_settings", updates=changes)


@router.get("/filings/retention", summary="Every filing with how long it must be kept (the archive view)")
def retention_register(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.record_retention import register
    return {"filings": register(session, ctx["org"]["org_id"])}


@router.get("/filings/preflight", summary="Confirm-data step: coverage, headline & gaps before freezing a filing")
def preflight(framework: str, session: DbSession, entity_id: Optional[str] = None, fund_id: Optional[str] = None,
              ctx: dict = Depends(require_permission("reports.view"))):
    """entity_id: the scope being filed (a legal entity, or a group consolidated over its subtree); omitted = the
    whole organisation. fund_id: the financial product a per-product report discloses. The figures and the confirm
    token are for exactly that book."""
    try:
        return F.preflight(session, ctx["org"]["org_id"], ctx["org"]["type"], framework, entity_id, fund_id)
    except F.FilingError as e:
        raise HTTPException(409, {"error": "filing_error", "message": str(e)})


@router.get("/filings/{filing_id}", summary="One filing — status, full history, and the frozen report")
def get_filing(filing_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    f = F.get_filing(session, ctx["org"]["org_id"], filing_id)
    if not f:
        raise HTTPException(404, {"error": "not_found", "message": "Filing not found."})
    return f


@router.get("/filings/{filing_id}/export", summary="Download the filing rendered from its FROZEN snapshot")
def export_filing(filing_id: str, format: str, session: DbSession,
                  ctx: dict = Depends(require_permission("reports.view"))):
    from fastapi.responses import StreamingResponse

    from services.governance.filing_export import ExportError
    from services.governance.filing_export import export_filing as _export
    try:
        filename, media_type, content = _export(session, ctx["org"]["org_id"], filing_id, format)
    except ExportError as e:
        raise HTTPException(404 if "not found" in str(e) else 409, {"error": "export_error", "message": str(e)})
    return StreamingResponse(iter([content]), media_type=media_type,
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/filings/{filing_id}/assurance-pack", summary="Auditor-ready evidence bundle (ZIP) for a filing")
def filing_assurance_pack(filing_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    import io

    from fastapi.responses import StreamingResponse
    from sqlalchemy import text

    from api.services.rbac import write_audit
    from services.governance.assurance_pack import build_assurance_pack
    org_id = ctx["org"]["org_id"]
    sid = session.execute(text("SELECT snapshot_id::text FROM regulatory_filing WHERE filing_id = CAST(:f AS uuid) AND org_id = CAST(:o AS uuid)"),
                          {"f": filing_id, "o": org_id}).scalar()
    if not sid:
        raise HTTPException(409, {"error": "no_snapshot", "message": "This filing has no frozen snapshot yet — prepare it first."})
    out = build_assurance_pack(session, org_id, sid)
    if not out:
        raise HTTPException(404, {"error": "not_found", "message": "No such snapshot for this organization."})
    fname, data = out
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="reports.assurance_pack.export",
                target_type="regulatory_filing", target_id=filing_id, detail={"file": fname})
    return StreamingResponse(io.BytesIO(data), media_type="application/zip",
                             headers={"Content-Disposition": f"attachment; filename={fname}"})


@router.get("/filings/{filing_id}/validation", summary="Run the pre-submission validation checklist")
def validation(filing_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.filing_validation import validate_filing
    try:
        return validate_filing(session, ctx["org"]["org_id"], filing_id)
    except ValueError as e:
        raise HTTPException(404, {"error": "not_found", "message": str(e)})


@router.get("/filings/{filing_id}/lineage/hazards", summary="The hazard cells a filing reports (trace entry points)")
def lineage_hazards(filing_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.filing_lineage import hazards_view
    try:
        return hazards_view(session, ctx["org"]["org_id"], filing_id)
    except ValueError as e:
        raise HTTPException(404, {"error": "not_found", "message": str(e)})


@router.get("/filings/{filing_id}/lineage", summary="Forward trace: a reported cell → assets → golden source → feeds")
def lineage(filing_id: str, hazard: str, session: DbSession,
            ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.filing_lineage import cell_lineage
    try:
        return cell_lineage(session, ctx["org"]["org_id"], filing_id, hazard)
    except ValueError as e:
        raise HTTPException(404, {"error": "not_found", "message": str(e)})


@router.get("/lineage/cell/{h3_cell}", summary="Reverse trace: a granular cell → every holding & filing that reuses it")
def lineage_cell(h3_cell: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.filing_lineage import cell_upstream
    return cell_upstream(session, ctx["org"]["org_id"], h3_cell)


@router.get("/filings/{filing_id}/retention", summary="How long this filing must be kept, and under which law")
def retention(filing_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.record_retention import RetentionError, retention_for
    try:
        return retention_for(session, ctx["org"]["org_id"], filing_id)
    except RetentionError as e:
        raise HTTPException(404, {"error": "not_found", "message": str(e)})


class HoldBody(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


@router.post("/filings/{filing_id}/legal-hold", summary="Put a filing on legal hold (it cannot be archived)")
def legal_hold(filing_id: str, body: HoldBody, session: DbSession, ctx: dict = Depends(require_permission("approvals.create"))):
    from services.governance.record_retention import RetentionError, set_hold
    try:
        out = set_hold(session, ctx["org"]["org_id"], filing_id, ctx["user"]["id"], body.reason)
    except RetentionError as e:
        raise HTTPException(409, {"error": "legal_hold", "message": str(e)})
    _audit(session, ctx, "filing.legal_hold.set", filing_id, {"reason": body.reason})
    session.commit()
    return out


@router.post("/filings/{filing_id}/legal-hold/lift", summary="Ask a second person to lift a legal hold")
def legal_hold_lift(filing_id: str, body: HoldBody, session: DbSession, ctx: dict = Depends(require_permission("approvals.create"))):
    from services.governance.record_retention import RetentionError, request_lift
    try:
        out = request_lift(session, ctx["org"]["org_id"], filing_id, ctx["user"]["id"], body.reason)
    except RetentionError as e:
        raise HTTPException(409, {"error": "legal_hold", "message": str(e)})
    _audit(session, ctx, "approval.create", out["approval_request_id"], {"request_type": "filing.legal_hold_lift"})
    session.commit()
    return out


@router.get("/filings/{filing_id}/data-revisions", summary="New data since this filing was frozen (it may need restating)")
def data_revisions(filing_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.data_revisions import revisions
    try:
        return revisions(session, ctx["org"]["org_id"], filing_id)
    except ValueError as e:
        raise HTTPException(404, {"error": "not_found", "message": str(e)})


@router.get("/filings/{filing_id}/variance", summary="Decompose how the numbers moved vs the prior filing")
def variance(filing_id: str, session: DbSession, vs: Optional[str] = None,
             ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.filing_variance import variance as _variance
    try:
        return _variance(session, ctx["org"]["org_id"], filing_id, vs_filing_id=vs)
    except ValueError as e:
        raise HTTPException(404, {"error": "not_found", "message": str(e)})


@router.post("/filings/{filing_id}/restate", status_code=201,
             summary="Restate a filed filing — freeze a new draft and supersede the old")
def restate(filing_id: str, body: RestateBody, session: DbSession,
            ctx: dict = Depends(require_permission("reports.publish"))):
    try:
        f = F.restate_filing(session, ctx["org"]["org_id"], filing_id, ctx["user"]["id"], body.reason)
    except F.FilingError as e:
        raise HTTPException(409, {"error": "filing_error", "message": str(e)})
    _audit(session, ctx, "filing.restate", filing_id, {"reason": body.reason, "new_filing_id": f["filing_id"]})
    return f


@router.post("/filings/{filing_id}/withdraw", summary="Withdraw a draft filing generated by mistake (frees its slot)")
def withdraw(filing_id: str, body: WithdrawBody, session: DbSession,
             ctx: dict = Depends(require_permission("approvals.create"))):
    try:
        f = F.withdraw_filing(session, ctx["org"]["org_id"], filing_id, ctx["user"]["id"], body.reason)
    except F.FilingError as e:
        raise HTTPException(409, {"error": "filing_error", "message": str(e)})
    _audit(session, ctx, "filing.withdraw", filing_id, {"reason": body.reason.strip()})
    return f


@router.post("/filings/{filing_id}/refresh", summary="Re-freeze a draft filing's data from the current book")
def refresh(filing_id: str, session: DbSession, ctx: dict = Depends(require_permission("approvals.create"))):
    try:
        f = F.refresh_filing(session, ctx["org"]["org_id"], filing_id, ctx["user"]["id"])
    except F.FilingError as e:
        raise HTTPException(409, {"error": "filing_error", "message": str(e)})
    _audit(session, ctx, "filing.refresh", filing_id)
    return f


# ── lifecycle ───────────────────────────────────────────────────────────

@router.post("/filings", status_code=201, summary="Generate a draft filing (freezes the report)")
def generate(body: GenerateBody, session: DbSession,
             ctx: dict = Depends(require_permission("approvals.create"))):
    try:
        f = F.generate_filing(session, ctx["org"]["org_id"], ctx["org"]["type"],
                              body.framework, ctx["user"]["id"], note=body.note,
                              confirm_token=body.confirm_token, entity_id=body.entity_id, view=body.view,
                              figure_sources=body.figure_sources, obligation_id=body.obligation_id,
                              fund_id=body.fund_id)
    except F.FilingError as e:
        raise HTTPException(409, {"error": "filing_error", "message": str(e)})
    _audit(session, ctx, "filing.generate", f["filing_id"], {"framework": body.framework, "entity_id": body.entity_id,
                                                            "view": body.view, "figure_sources": body.figure_sources})
    return f


@router.post("/filings/{filing_id}/submit-for-review", summary="Submit a draft for 4-eyes approval (maker)")
def submit_for_review(filing_id: str, session: DbSession,
                      ctx: dict = Depends(require_permission("approvals.create"))):
    try:
        f = F.submit_for_review(session, ctx["org"]["org_id"], filing_id, ctx["user"]["id"])
    except F.FilingError as e:
        raise HTTPException(409, {"error": "filing_error", "message": str(e)})
    _audit(session, ctx, "filing.submit_for_review", filing_id)
    return f


@router.post("/filings/{filing_id}/attest", summary="Attest the filing — named accountable sign-off")
def attest(filing_id: str, body: AttestBody, session: DbSession,
           ctx: dict = Depends(require_permission("board.attest"))):
    # The attestor is always the CALLING user's own name on file — never client-supplied (see module
    # docstring). Falls back to email only in the unlikely case full_name is blank, so attestation is never
    # recorded against an empty string.
    attestor_name = ctx["user"].get("full_name") or ctx["user"]["email"]
    try:
        f = F.attest(session, ctx["org"]["org_id"], filing_id, ctx["user"]["id"],
                     attestor_name, body.statement)
    except F.FilingError as e:
        raise HTTPException(409, {"error": "filing_error", "message": str(e)})
    _audit(session, ctx, "filing.attest", filing_id, {"attestor_name": attestor_name})
    return f


@router.post("/filings/{filing_id}/submit", summary="Transmit the filing to the regulator")
def submit(filing_id: str, body: SubmitBody, session: DbSession,
           ctx: dict = Depends(require_permission("reports.publish"))):
    try:
        f = F.submit(session, ctx["org"]["org_id"], filing_id, ctx["user"]["id"], body.submission_ref)
    except F.FilingError as e:
        raise HTTPException(409, {"error": "filing_error", "message": str(e)})
    _audit(session, ctx, "filing.submit", filing_id, {"submission_ref": body.submission_ref})
    return f


@router.post("/filings/{filing_id}/accept", summary="Record the regulator's acknowledgement")
def accept(filing_id: str, body: AcceptBody, session: DbSession,
           ctx: dict = Depends(require_permission("reports.publish"))):
    try:
        f = F.accept(session, ctx["org"]["org_id"], filing_id, ctx["user"]["id"], body.ack_ref)
    except F.FilingError as e:
        raise HTTPException(409, {"error": "filing_error", "message": str(e)})
    _audit(session, ctx, "filing.accept", filing_id, {"ack_ref": body.ack_ref})
    return f
