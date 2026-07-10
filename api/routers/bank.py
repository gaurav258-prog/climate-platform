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
    return org_id or DEMO_ORG


OrgId = Annotated[str, Depends(resolve_org)]


def _assets_with_risk(session, org_id, scenario, horizon, severity_model="universal"):
    """All of an org's assets (metadata) + their per-hazard projected risk.
    severity_model: org_calc_settings' choice ('universal' default, or
    'peril_specific' -- see ml/scoring/valuation_discount.py). Thin wrapper
    over the shared portfolio engine (services/portfolio_engine.py) -- the
    fetch/join/headline/valuation logic itself lives there, shared with
    real estate and asset management."""
    rows = fetch_entities_with_risk(session, org_id, "banking", scenario, horizon, severity_model,
                                     ext_table="ext_banking", ext_columns=EXT_BANKING_COLUMNS,
                                     valuation_kwargs=_ltv_kwargs)
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


def build_disclosure_snapshot(session, org_id, scenario, horizon):
    """The single source of truth for a TCFD/EU-Taxonomy disclosure: live callers
    (GET /disclosure) and frozen callers (submission snapshots) both go through
    this, so a submission's numbers can never drift from what the live view shows
    at the moment it's taken."""
    severity_model = get_calc_settings(session, org_id)["severity_model"]
    assets = _assets_with_risk(session, org_id, scenario, horizon, severity_model)
    return {
        "rollup": _rollup(assets),
        "assets": assets,
        **_hazard_rollup(assets),
    }


@router.get("/disclosure", summary="TCFD / EU-Taxonomy disclosure pack from the projected book")
def disclosure(session: DbSession, org_id: OrgId,
               scenario: str = Query("baseline"), horizon: str = Query("current")):
    snapshot = build_disclosure_snapshot(session, org_id, scenario, horizon)
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
    {"name": "asset_name", "required": True, "description": "Free-text asset/property name.", "example": "Frankfurt Tower 1"},
    {"name": "asset_type", "required": True, "description": "Property/collateral type.", "example": "commercial_real_estate"},
    {"name": "latitude", "required": True, "description": "Decimal degrees.", "example": "50.1109"},
    {"name": "longitude", "required": True, "description": "Decimal degrees.", "example": "8.6821"},
    {"name": "appraised_value_eur", "required": True, "description": "Current appraised/collateral value.", "example": "12000000"},
    {"name": "sector", "required": True, "description": "Sector / NACE classification.", "example": "Commercial real estate"},
    {"name": "outstanding_loan_balance_eur", "required": False, "description": "Current outstanding principal — enables LTV.", "example": "8400000"},
    {"name": "loan_origination_date", "required": False, "description": "YYYY-MM-DD.", "example": "2022-03-01"},
    {"name": "region", "required": False, "description": "Free-text region/city.", "example": "Frankfurt"},
    {"name": "country", "required": False, "description": "ISO-2 country code.", "example": "DE"},
    {"name": "borrower_entity_id", "required": False, "description": "Borrower's LEI or other stable entity ID — "
     "lets a minimum-safeguards compliance flag be matched/refreshed by entity rather than re-collected per loan.", "example": "5493001KJTIIGC8Y1R12"},
    {"name": "minimum_safeguards_status", "required": False, "description": "compliant / non_compliant, from your own "
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


@router.post("/assets/upload", summary="Bulk-upload assets from a CSV into your loan book")
async def upload_assets(session: DbSession, ctx: CurrentUser, file: UploadFile = File(...)):
    """Real self-service data entry: a CSV of assets lands in the uploader's OWN
    org (never DEMO_ORG — this always requires a real login), gets an H3 cell per
    row, and is immediately processed against the golden source (see
    services.scoring.on_demand.process_new_cells) exactly the way an any-address
    lookup query would be -- no separate ingestion pipeline to keep in sync."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")
    raw = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}")

    missing = [c for c in REQUIRED_ASSET_COLUMNS if c not in df.columns]
    if missing:
        raise HTTPException(status_code=400, detail={"error": "missing_columns", "missing": missing})

    org_id = ctx["org"]["org_id"]
    records, cell_coords = [], {}
    for _, row in df.iterrows():
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
            value_eur = float(row["appraised_value_eur"])
        except (TypeError, ValueError):
            continue  # a row with an unparsable required field is skipped, not fatal to the whole upload
        cell = h3.latlng_to_cell(lat, lon, 8)
        cell_coords[cell] = (lat, lon)
        outstanding = row.get("outstanding_loan_balance_eur")
        origination = row.get("loan_origination_date")
        safeguards = str(row["minimum_safeguards_status"]).strip().lower() if "minimum_safeguards_status" in df.columns and pd.notna(row.get("minimum_safeguards_status")) else None
        if safeguards and safeguards not in SAFEGUARDS_STATUSES:
            safeguards = None
        records.append({
            "entity_id": str(uuid.uuid4()), "org_id": org_id,
            "entity_name": str(row["asset_name"]), "entity_type": str(row["asset_type"]),
            "latitude": lat, "longitude": lon, "h3_cell": cell,
            "region": str(row["region"]) if "region" in df.columns and pd.notna(row.get("region")) else None,
            "country": str(row["country"]) if "country" in df.columns and pd.notna(row.get("country")) else None,
            "primary_value_eur": value_eur, "sector": str(row["sector"]),
            "outstanding_loan_balance_eur": float(outstanding) if pd.notna(outstanding) else None,
            "loan_origination_date": str(origination)[:10] if pd.notna(origination) else None,
            "borrower_entity_id": str(row["borrower_entity_id"]) if "borrower_entity_id" in df.columns and pd.notna(row.get("borrower_entity_id")) else None,
            "minimum_safeguards_status": safeguards,
            # No nace_code in today's upload template, so real EU Taxonomy classification
            # (ml/regulatory/eu_taxonomy_classifier.py) can't run yet -- honest "not assessed",
            # never a guessed status, even with minimum_safeguards_status on file. Adding a
            # nace_code column is a natural follow-on.
            "taxonomy_status": "not_assessed",
        })
    if not records:
        raise HTTPException(status_code=400, detail="No valid rows found in the uploaded CSV")

    session.execute(text("""
        INSERT INTO portfolio_entities (entity_id, org_id, vertical, entity_name, entity_type, latitude, longitude,
                                         h3_cell, region, country, primary_value_eur, sector,
                                         borrower_entity_id, minimum_safeguards_status)
        VALUES (:entity_id, :org_id, 'banking', :entity_name, :entity_type, :latitude, :longitude,
                :h3_cell, :region, :country, :primary_value_eur, :sector,
                :borrower_entity_id, :minimum_safeguards_status)
    """), records)
    session.execute(text("""
        INSERT INTO ext_banking (entity_id, outstanding_loan_balance_eur, loan_origination_date, taxonomy_status)
        VALUES (:entity_id, :outstanding_loan_balance_eur, :loan_origination_date, :taxonomy_status)
    """), records)
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="assets.upload",
                target_type="bank_assets", target_id=None,
                detail={"n_rows": len(records), "filename": file.filename})

    processing = process_new_cells(cell_coords)
    return {"n_uploaded": len(records), **processing}


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
