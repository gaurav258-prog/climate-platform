"""
Banking flagship — public read-only endpoints for the loan-book workspace.

Projects the golden source (canonical_scores) onto a bank's assets by H3 cell,
via the shared portfolio engine (services/portfolio_engine.py) and the unified
v_portfolio_entity_physical_risk view -- the same engine real estate and asset
management use, so a fix or a new calc-settings trigger only needs writing once
(see the b9c0d1e2f3a4 migration's docstring for the duplication this replaced).
Every figure carries its model_version + vintage so the disclosure is
defensible. No auth (aggregate read), mirroring platform.py.
"""
from __future__ import annotations

import io
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from typing import Annotated, Optional

import h3
import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import CurrentUser, DbSession
from api.services.rbac import write_audit
from services.calc_settings import get_calc_settings
from services.portfolio_engine import (
    apply_valuation_override as engine_apply_override,
    clear_valuation_override as engine_clear_override,
    fetch_entities_with_risk, get_entity_org, get_entity_with_risk,
)
from services.scoring.on_demand import process_new_cells
from services.templates.workbook import build_export_workbook, build_template_workbook

EXT_BANKING_COLUMNS = [
    "CAST(x.annual_revenue_eur AS FLOAT) AS annual_revenue_eur",
    "x.taxonomy_status", "x.taxonomy_activity", "x.dnsh_assessment",
    "x.expected_lifespan_years", "x.gics_code",
    "CAST(x.ghg_emissions_scope1_tco2e AS FLOAT) AS ghg_emissions_scope1_tco2e",
    "CAST(x.ghg_emissions_scope2_tco2e AS FLOAT) AS ghg_emissions_scope2_tco2e",
    "CAST(x.ghg_emissions_scope3_tco2e AS FLOAT) AS ghg_emissions_scope3_tco2e",
    "CAST(x.outstanding_loan_balance_eur AS FLOAT) AS outstanding_loan_balance_eur",
    "x.loan_origination_date",
    # per-loan attributes the customer provides (Data → provide by Excel): feed the Pillar 3 integrated cells
    "CAST(x.residual_maturity_years AS FLOAT) AS residual_maturity_years",
    "x.epc_label", "x.ifrs9_stage",
]


def _ltv_kwargs(row):
    return {"outstanding_balance_eur": row.get("outstanding_loan_balance_eur")}


def _map_asset_list_row(row):
    """Shared-engine row -> the exact shape /portfolio, /summary, /disclosure
    have always returned (frontend + frozen submission snapshots rely on
    these exact field names, so this rename is the ENTIRE cost of sharing
    the fetch/join/headline/valuation layer with the other 3 verticals)."""
    return {
        "asset_id": row["entity_id"], "asset_name": row["entity_name"], "asset_type": row["entity_type"],
        "sector": row["sector"], "country": row["country"], "region": row["region"],
        "lat": row["lat"], "lon": row["lon"], "h3_cell": row["h3_cell"],
        "value_eur": row["primary_value_eur"],
        "revenue_eur": row["annual_revenue_eur"], "taxonomy_status": row["taxonomy_status"],
        "construction_year": row["year_built"], "nace_code": row["nace_code"],
        "ghg1": row["ghg_emissions_scope1_tco2e"], "ghg2": row["ghg_emissions_scope2_tco2e"],
        "ghg3": row["ghg_emissions_scope3_tco2e"],
        "outstanding_loan_balance_eur": row["outstanding_loan_balance_eur"],
        "loan_origination_date": row["loan_origination_date"],
        "residual_maturity_years": row.get("residual_maturity_years"),
        "epc_label": row.get("epc_label"), "ifrs9_stage": row.get("ifrs9_stage"),
        "hazards": row["hazards"], "headline_score": row["headline_score"],
        "headline_bucket": row["headline_bucket"], "headline_hazard": row["headline_hazard"],
        "valuation": row["valuation"],
    }

router = APIRouter(prefix="/v1/bank", tags=["Banking"])

DEMO_ORG = "11111111-1111-4111-8111-111111111111"
BUCKET_RANK = {"VH": 4, "H": 3, "M": 2, "L": 1}

_bearer = HTTPBearer(auto_error=False)


def resolve_org(
    org_id: Optional[str] = Query(None),
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)] = None,
) -> str:
    """
    Tenant scoping: a user JWT's org wins (real isolation); otherwise fall back to
    the org_id query param, and finally to DEMO_ORG so the public marketing/demo
    path keeps working without a token.
    """
    token = credentials.credentials if credentials else None
    if token and not token.startswith("cp_live_"):
        from api.security import decode_access_token
        payload = decode_access_token(token)
        if payload and payload.get("org_id"):
            return payload["org_id"]
    # SECURITY: a caller without a valid user JWT can ONLY ever see the public
    # demo org — never an arbitrary org_id. Dropping the query-param fallback
    # closes the cross-tenant read (an anonymous ?org_id=<other-tenant> IDOR).
    return DEMO_ORG


OrgId = Annotated[str, Depends(resolve_org)]


def _assets_with_risk(session, org_id, scenario, horizon, severity_model="universal",
                      entity_ids=None, value_weights=None):
    """All of an org's assets (metadata) + their per-hazard projected risk.
    severity_model: org_calc_settings' choice ('universal' default, or
    'peril_specific' -- see ml/scoring/valuation_discount.py). Thin wrapper
    over the shared portfolio engine (services/portfolio_engine.py) -- the
    fetch/join/headline/valuation logic itself lives there, shared with
    real estate and asset management. entity_ids / value_weights scope +
    consolidation-weight the book for per-entity / group filings."""
    rows = fetch_entities_with_risk(session, org_id, "banking", scenario, horizon, severity_model,
                                     ext_table="ext_banking", ext_columns=EXT_BANKING_COLUMNS,
                                     valuation_kwargs=_ltv_kwargs,
                                     entity_ids=entity_ids, value_weights=value_weights)
    return [_map_asset_list_row(r) for r in rows]


def _rollup(assets):
    total = sum(a["value_eur"] or 0 for a in assets)
    at_risk = [a for a in assets if a["headline_bucket"] in ("H", "VH")]
    var = sum(a["value_eur"] or 0 for a in at_risk)
    total_discounted = sum(a["valuation"]["discounted_value_eur"] for a in assets)
    by_bucket = defaultdict(lambda: {"count": 0, "value": 0.0})
    for a in assets:
        b = a["headline_bucket"] or "none"
        by_bucket[b]["count"] += 1
        by_bucket[b]["value"] += a["value_eur"] or 0
    return {
        "n_assets": len(assets),
        "n_scored": sum(1 for a in assets if a["headline_bucket"]),
        "total_value_eur": round(total),
        "value_at_risk_eur": round(var),
        "pct_value_at_risk": round(100 * var / total, 1) if total else 0,
        "n_high": len(at_risk),
        "total_discounted_value_eur": round(total_discounted),
        "n_overridden": sum(1 for a in assets if a["valuation"]["is_overridden"]),
        "by_bucket": {k: {"count": v["count"], "value_eur": round(v["value"])} for k, v in by_bucket.items()},
        "top_assets": sorted(
            [a for a in assets if a["headline_score"] is not None],
            key=lambda a: -a["headline_score"])[:8],
    }


@router.get("/portfolio", summary="Loan book projected onto the golden source")
def portfolio(session: DbSession, org_id: OrgId,
              scenario: str = Query("baseline"), horizon: str = Query("current")):
    severity_model = get_calc_settings(session, org_id)["severity_model"]
    assets = _assets_with_risk(session, org_id, scenario, horizon, severity_model)
    return {"org_id": org_id, "scenario": scenario, "horizon": horizon,
            "rollup": _rollup(assets), "assets": assets}


@router.get("/forward-risk", summary="Forward-change decision signal — scenario risk migration + runway")
def forward_risk_ep(session: DbSession, org_id: OrgId, scenario: str = Query("disorderly_2c")):
    from services.intelligence.forward_risk import forward_risk
    return forward_risk(session, org_id, "banking", scenario)


@router.get("/expected-loss", summary="Climate expected loss (€) — annual + lifetime, maturity-matched")
def expected_loss_ep(session: DbSession, org_id: OrgId, scenario: str = Query("disorderly_2c")):
    from services.intelligence.expected_loss import bank_expected_loss
    return bank_expected_loss(session, org_id, scenario)


@router.get("/summary", summary="Command-center rollup")
def summary(session: DbSession, org_id: OrgId,
            scenario: str = Query("baseline"), horizon: str = Query("current")):
    org = session.execute(text(
        "SELECT name, type, country FROM organizations WHERE org_id = :o"
    ), {"o": org_id}).mappings().first()
    severity_model = get_calc_settings(session, org_id)["severity_model"]
    assets = _assets_with_risk(session, org_id, scenario, horizon, severity_model)
    return {"org_id": org_id, "org": dict(org) if org else None, "rollup": _rollup(assets)}


def _hazard_rollup(assets):
    """Physical risk by hazard, EU-Taxonomy alignment and financed emissions —
    the three blocks the TCFD/EU-Taxonomy disclosure pack adds on top of _rollup()."""
    # physical risk by hazard — value of the book exposed at High+ per hazard
    hazards: dict = {}
    for a in assets:
        for hz in a["hazards"]:
            h = hazards.setdefault(hz["hazard"], {
                "exposed_value_eur": 0.0, "n_exposed": 0, "max_score": 0.0,
                "model_version": hz["model_version"], "scored_at": hz["scored_at"]})
            if hz["bucket"] in ("H", "VH"):
                h["exposed_value_eur"] += a["value_eur"] or 0
                h["n_exposed"] += 1
            h["max_score"] = max(h["max_score"], hz["score"])
    for h in hazards.values():
        h["exposed_value_eur"] = round(h["exposed_value_eur"])
        h["max_score"] = round(h["max_score"], 1)
    # EU-Taxonomy alignment, value-weighted
    tax = defaultdict(lambda: {"count": 0, "value_eur": 0.0})
    for a in assets:
        t = a.get("taxonomy_status") or "unknown"
        tax[t]["count"] += 1
        tax[t]["value_eur"] += a["value_eur"] or 0
    # financed emissions (GHG totals across the book)
    ghg = {f"scope{i}": round(sum((a.get(f"ghg{i}") or 0) for a in assets))
           for i in (1, 2, 3)}
    return {
        "by_hazard": hazards,
        "taxonomy": {k: {"count": v["count"], "value_eur": round(v["value_eur"])} for k, v in tax.items()},
        "financed_emissions_tco2e": ghg,
    }


def build_disclosure_snapshot(session, org_id, scenario, horizon, entity_ids=None, value_weights=None):
    """The single source of truth for a TCFD/EU-Taxonomy disclosure: live callers
    (GET /disclosure) and frozen callers (submission snapshots) both go through
    this, so a submission's numbers can never drift from what the live view shows
    at the moment it's taken. entity_ids / value_weights scope + consolidation-weight
    the book for a per-entity or consolidated-group filing (None = whole org)."""
    severity_model = get_calc_settings(session, org_id)["severity_model"]
    assets = _assets_with_risk(session, org_id, scenario, horizon, severity_model,
                               entity_ids=entity_ids, value_weights=value_weights)
    return {
        "rollup": _rollup(assets),
        "assets": assets,
        **_hazard_rollup(assets),
    }


@router.get("/disclosure", summary="TCFD / EU-Taxonomy disclosure pack from the projected book")
def disclosure(session: DbSession, org_id: OrgId,
               scenario: str = Query("baseline"), horizon: str = Query("current"),
               slim: bool = Query(False, description="omit the per-asset array (aggregates only) — for the "
                                                     "Analytics scenario grid, which needs only the totals")):
    snapshot = build_disclosure_snapshot(session, org_id, scenario, horizon)
    if slim:
        snapshot.pop("assets", None)
    return {"org_id": org_id, "scenario": scenario, "horizon": horizon, **snapshot}


@router.get("/asset/{asset_id}", summary="One asset — full projection + provenance")
def asset_detail(asset_id: str, session: DbSession):
    org_id = get_entity_org(session, asset_id)
    if not org_id:
        return {"error": "asset not found"}
    severity_model = get_calc_settings(session, org_id)["severity_model"]
    # Pre-existing quirk, preserved exactly: this endpoint has no scenario/horizon
    # params, so its headline is picked across EVERY scenario/horizon this asset
    # has ever been scored under (scope_headline_to_query=False) -- can disagree
    # with the portfolio list's scenario-scoped headline for the same asset.
    row = get_entity_with_risk(session, asset_id, "baseline", "current", severity_model,
                                ext_table="ext_banking", ext_columns=EXT_BANKING_COLUMNS,
                                valuation_kwargs=_ltv_kwargs, scope_headline_to_query=False)
    asset = {
        "asset_id": row["entity_id"], "org_id": row["org_id"], "asset_name": row["entity_name"],
        "asset_type": row["entity_type"], "sector": row["sector"], "country": row["country"],
        "region": row["region"], "lat": row["lat"], "lon": row["lon"], "h3_cell": row["h3_cell"],
        "value_eur": row["primary_value_eur"], "revenue_eur": row["annual_revenue_eur"],
        "taxonomy_status": row["taxonomy_status"], "taxonomy_activity": row["taxonomy_activity"],
        "dnsh_assessment": row["dnsh_assessment"], "construction_year": row["year_built"],
        "expected_lifespan_years": row["expected_lifespan_years"], "nace_code": row["nace_code"],
        "gics_code": row["gics_code"],
        "ghg_scope1": row["ghg_emissions_scope1_tco2e"], "ghg_scope2": row["ghg_emissions_scope2_tco2e"],
        "ghg_scope3": row["ghg_emissions_scope3_tco2e"],
        "outstanding_loan_balance_eur": row["outstanding_loan_balance_eur"],
        "loan_origination_date": row["loan_origination_date"],
        "borrower_entity_id": row["borrower_entity_id"], "minimum_safeguards_status": row["minimum_safeguards_status"],
    }
    audit = session.execute(text("""
        SELECT actor_user_id::text AS actor_user_id, action, detail, created_at
        FROM access_audit_log WHERE target_type = 'bank_asset' AND target_id = :a
        ORDER BY created_at DESC LIMIT 5
    """), {"a": asset_id}).mappings().all()
    return {
        "asset": asset, "risks": row["risks"], "valuation": row["valuation"],
        "valuation_audit": [dict(x) for x in audit],
    }


class ValuationOverrideRequest(BaseModel):
    discount_pct: float = Field(..., ge=0, le=100)
    reason: Optional[str] = None


@router.post("/asset/{asset_id}/valuation-override", summary="Override the recommended valuation discount (audited)")
def override_valuation(asset_id: str, body: ValuationOverrideRequest, session: DbSession, ctx: CurrentUser):
    if "pricing.approve" not in ctx["permissions"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Missing permission: pricing.approve"})
    org_id = get_entity_org(session, asset_id)
    if not org_id:
        raise HTTPException(status_code=404, detail="asset not found")
    if org_id != ctx["org"]["org_id"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Asset does not belong to your organization"})

    result = engine_apply_override(session, asset_id, body.discount_pct, ctx["user"]["id"], body.reason)
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="asset.valuation.override", target_type="bank_asset", target_id=asset_id,
                detail={"from_pct": result["from_pct"], "to_pct": body.discount_pct, "reason": body.reason})
    return {"asset_id": asset_id, "override_discount_pct": body.discount_pct,
            "overridden_at": result["overridden_at"].isoformat()}


@router.delete("/asset/{asset_id}/valuation-override", summary="Clear an override, revert to the recommended discount (audited)")
def clear_asset_valuation_override(asset_id: str, session: DbSession, ctx: CurrentUser):
    if "pricing.approve" not in ctx["permissions"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Missing permission: pricing.approve"})
    prior = engine_clear_override(session, asset_id)
    if not prior:
        return {"asset_id": asset_id, "cleared": False}
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="asset.valuation.override_cleared", target_type="bank_asset", target_id=asset_id,
                detail={"from_pct": prior["override_discount_pct"], "to_pct": None})
    return {"asset_id": asset_id, "cleared": True}


# A real "loan tape" -- see ml/scoring/valuation_discount.py's LTV functions and
# services/templates/workbook.py's template. appraised_value_eur is the CSV/
# template-facing name (industry-recognizable); it maps onto the existing
# asset_value_eur DB column (a disclosed rename, not a churny migration).
ASSET_TEMPLATE_FIELDS = [
    {"name": "asset_name", "required": True, "label": "Asset name", "kind": "text", "description": "Free-text asset/property name.", "example": "Frankfurt Tower 1"},
    {"name": "asset_type", "required": True, "label": "Asset type", "kind": "text", "description": "Property/collateral type.", "example": "commercial_real_estate"},
    {"name": "latitude", "required": True, "label": "Latitude", "kind": "lat", "description": "Decimal degrees.", "example": "50.1109"},
    {"name": "longitude", "required": True, "label": "Longitude", "kind": "lon", "description": "Decimal degrees.", "example": "8.6821"},
    {"name": "appraised_value_eur", "required": True, "label": "Appraised value (EUR)", "kind": "money", "description": "Current appraised/collateral value.", "example": "12000000"},
    {"name": "sector", "required": True, "label": "Sector", "kind": "text", "description": "Sector / NACE classification.", "example": "Commercial real estate"},
    {"name": "outstanding_loan_balance_eur", "required": False, "label": "Outstanding loan balance (EUR)", "kind": "money", "description": "Current outstanding principal — enables LTV.", "example": "8400000"},
    {"name": "loan_origination_date", "required": False, "label": "Loan origination date", "kind": "date", "description": "YYYY-MM-DD.", "example": "2022-03-01"},
    {"name": "region", "required": False, "label": "Region", "kind": "text", "description": "Free-text region/city.", "example": "Frankfurt"},
    {"name": "country", "required": False, "label": "Country", "kind": "iso2", "description": "ISO-2 country code.", "example": "DE"},
    {"name": "borrower_entity_id", "required": False, "label": "Borrower ID (LEI)", "kind": "text", "description": "Borrower's LEI or other stable entity ID — "
     "lets a minimum-safeguards compliance flag be matched/refreshed by entity rather than re-collected per loan.", "example": "5493001KJTIIGC8Y1R12"},
    {"name": "minimum_safeguards_status", "required": False, "label": "Minimum-safeguards status", "kind": "text", "description": "compliant / non_compliant, from your own "
     "OECD/UN/ILO counterparty screening — enables a real EU Taxonomy minimum-safeguards check (also requires a "
     "nace_code on the loan, which today's upload doesn't yet collect — see the taxonomy_status note below).", "example": "compliant"},
]
REQUIRED_ASSET_COLUMNS = [f["name"] for f in ASSET_TEMPLATE_FIELDS if f["required"]]
SAFEGUARDS_STATUSES = {"compliant", "non_compliant"}


@router.get("/assets/template.xlsx", summary="Download the loan-tape upload template (Excel)")
def assets_template_xlsx():
    buf = build_template_workbook(ASSET_TEMPLATE_FIELDS)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              headers={"Content-Disposition": "attachment; filename=tellumen_loan_tape_template.xlsx"})


def _report(raw: bytes, filename: Optional[str]) -> dict:
    """Parse (CSV or Excel) + validate a loan-tape upload — the shared step behind both the pre-import check and
    the import itself, so what you preview is exactly what gets saved."""
    from services.ingest.upload_validation import parse_table, validate_table
    df = parse_table(raw, filename)   # raises ValueError → clean 400 in the callers
    return validate_table(df, ASSET_TEMPLATE_FIELDS)


@router.post("/assets/validate", summary="Check a loan tape (CSV or Excel) before importing — nothing is saved")
async def validate_assets(ctx: CurrentUser, file: UploadFile = File(...)):
    """Dry run: report how many rows are ready and which need fixing (with a reason per row), without writing
    anything. The UI shows this as the pre-import preview; the preparer then confirms the import."""
    try:
        rep = _report(await file.read(), file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not rep["ok"]:
        raise HTTPException(status_code=400, detail={"error": "missing_columns", "missing_columns": rep["missing_columns"]})
    return {"filename": file.filename, "n_total": rep["n_total"], "n_valid": rep["n_valid"],
            "n_error": rep["n_error"], "errors": rep["errors"][:200]}


@router.post("/assets/upload", summary="Import a loan tape (CSV or Excel) into your loan book")
async def upload_assets(session: DbSession, ctx: CurrentUser, file: UploadFile = File(...)):
    """Imports the rows that pass validation and reports any that didn't — nothing invalid is silently dropped.
    Each imported asset lands in the uploader's OWN org, gets an H3 cell, and is scored against the golden source
    the same way an any-address lookup is (services.scoring.on_demand.process_new_cells)."""
    try:
        rep = _report(await file.read(), file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not rep["ok"]:
        raise HTTPException(status_code=400, detail={"error": "missing_columns", "missing_columns": rep["missing_columns"]})
    if rep["n_valid"] == 0:
        raise HTTPException(status_code=400, detail="None of the rows are ready to import yet — please fix the flagged rows and try again.")

    org_id = ctx["org"]["org_id"]
    from services.ingest.portfolio_ingest import ingest_bank_assets
    res = ingest_bank_assets(session, org_id, rep["valid_rows"])
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="assets.upload",
                target_type="bank_assets", target_id=None,
                detail={"n_rows": res["n_ingested"], "n_invalid": rep["n_error"], "filename": file.filename})

    return {"n_uploaded": res["n_ingested"], "n_skipped": res["n_skipped"], "n_invalid": rep["n_error"],
            "errors": rep["errors"][:200], **res["processing"]}


# ── Per-loan regulatory attributes the engine can't derive from location — provided in bulk by Excel, matched to
#    the book by asset name, and written to the loan's record (feeds Pillar 3 maturity/EPC/staging + expected loss).
ATTR_TEMPLATE_FIELDS = [
    {"name": "asset_name", "required": True, "label": "Asset name", "kind": "text", "description": "Must match an asset already in your book.", "example": "Frankfurt Tower 1"},
    {"name": "residual_maturity_years", "required": False, "label": "Residual maturity (years)", "kind": "money", "description": "Remaining life of the loan, in years.", "example": "7"},
    {"name": "epc_label", "required": False, "label": "EPC label", "kind": "enum", "allowed": ["A", "B", "C", "D", "E", "F", "G"], "description": "Energy Performance Certificate grade of the collateral.", "example": "C"},
    {"name": "ifrs9_stage", "required": False, "label": "IFRS-9 stage", "kind": "enum", "allowed": ["1", "2", "3"], "description": "IFRS-9 credit-risk stage.", "example": "1"},
]
_ATTR_COLS = {"residual_maturity_years", "epc_label", "ifrs9_stage"}


@router.get("/assets/attributes/template.xlsx", summary="Download the per-loan attributes template (Excel)")
def attributes_template_xlsx():
    buf = build_template_workbook(ATTR_TEMPLATE_FIELDS)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              headers={"Content-Disposition": "attachment; filename=tellumen_loan_attributes_template.xlsx"})


@router.post("/assets/attributes/validate", summary="Check a per-loan attributes file (CSV or Excel) before saving")
async def validate_attributes(ctx: CurrentUser, file: UploadFile = File(...)):
    from services.ingest.upload_validation import parse_and_validate
    try:
        rep = parse_and_validate(await file.read(), file.filename, ATTR_TEMPLATE_FIELDS)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not rep["ok"]:
        raise HTTPException(status_code=400, detail={"error": "missing_columns", "missing_columns": rep["missing_columns"]})
    return {"filename": file.filename, "n_total": rep["n_total"], "n_valid": rep["n_valid"],
            "n_error": rep["n_error"], "errors": rep["errors"][:200]}


@router.post("/assets/attributes/upload", summary="Save per-loan attributes, matched to your book by asset name")
async def upload_attributes(session: DbSession, ctx: CurrentUser, file: UploadFile = File(...)):
    """Matches each row to an existing asset by name (case-insensitive) and writes the provided attributes to the
    loan's record — the fields that pass validation only. Unmatched rows are reported, never guessed."""
    from services.ingest.upload_validation import parse_and_validate
    try:
        rep = parse_and_validate(await file.read(), file.filename, ATTR_TEMPLATE_FIELDS)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not rep["ok"]:
        raise HTTPException(status_code=400, detail={"error": "missing_columns", "missing_columns": rep["missing_columns"]})
    if rep["n_valid"] == 0:
        raise HTTPException(status_code=400, detail="None of the rows are ready yet — please fix the flagged rows and try again.")

    org_id = ctx["org"]["org_id"]
    # name → entity_id for this org's loan book (lower-cased for a forgiving match)
    idx = {r[0].strip().lower(): r[1] for r in session.execute(text(
        "SELECT entity_name, entity_id FROM portfolio_entities WHERE org_id = CAST(:o AS uuid) AND vertical = 'banking'"
    ), {"o": org_id}).fetchall()}

    matched, unmatched, updated = 0, [], 0
    for row in rep["valid_rows"]:
        name = str(row.get("asset_name") or "").strip()
        eid = idx.get(name.lower())
        if not eid:
            unmatched.append(name)
            continue
        matched += 1
        sets, params = [], {"e": eid}
        mat = row.get("residual_maturity_years")
        if mat not in (None, ""):
            sets.append("residual_maturity_years = :mat"); params["mat"] = float(str(mat).replace(",", ""))
        epc = row.get("epc_label")
        if epc not in (None, ""):
            sets.append("epc_label = :epc"); params["epc"] = str(epc).strip().upper()
        stg = row.get("ifrs9_stage")
        if stg not in (None, ""):
            sets.append("ifrs9_stage = :stg"); params["stg"] = str(stg).strip()
        if sets:
            session.execute(text(f"UPDATE ext_banking SET {', '.join(sets)} WHERE entity_id = :e"), params)
            updated += 1
    session.commit()
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="assets.attributes.upload",
                target_type="ext_banking", target_id=None,
                detail={"matched": matched, "updated": updated, "unmatched": len(unmatched), "filename": file.filename})
    return {"n_matched": matched, "n_updated": updated, "n_unmatched": len(unmatched),
            "unmatched": unmatched[:50], "n_invalid": rep["n_error"], "errors": rep["errors"][:200]}


@router.get("/disclosure.xlsx", summary="TCFD / EU-Taxonomy disclosure pack (Excel)")
def disclosure_xlsx(session: DbSession, org_id: OrgId,
                     scenario: str = Query("baseline"), horizon: str = Query("current")):
    severity_model = get_calc_settings(session, org_id)["severity_model"]
    assets = _assets_with_risk(session, org_id, scenario, horizon, severity_model)
    headers = ["asset_name", "sector", "country", "value_eur", "headline_score", "risk_bucket",
               "taxonomy_status", "h3_cell", "recommended_discount_pct", "effective_discount_pct",
               "discounted_value_eur", "overridden", "outstanding_loan_balance_eur",
               "original_ltv_pct", "climate_adjusted_ltv_pct"]
    rows = [[a["asset_name"], a["sector"], a["country"], a["value_eur"], a["headline_score"],
             a["headline_bucket"] or "unscored", a["taxonomy_status"], a["h3_cell"],
             a["valuation"]["recommended_discount_pct"], a["valuation"]["effective_discount_pct"],
             a["valuation"]["discounted_value_eur"], "yes" if a["valuation"]["is_overridden"] else "no",
             a["valuation"]["outstanding_loan_balance_eur"], a["valuation"]["original_ltv_pct"],
             a["valuation"]["climate_adjusted_ltv_pct"]] for a in assets]
    buf = build_export_workbook(headers, rows, sheet_name="Physical risk disclosure")
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              headers={"Content-Disposition": "attachment; filename=meridian-physical-risk-disclosure.xlsx"})
