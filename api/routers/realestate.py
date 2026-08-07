"""
Real estate — public read-only endpoints for the Portfolio & NOI impact
workspace, the platform's 4th vertical.

Projects the golden source (canonical_scores) onto a REIT's property book via
the shared portfolio engine (services/portfolio_engine.py) and the unified
v_portfolio_entity_physical_risk view -- the same engine banking and asset
management use (see the b9c0d1e2f3a4 migration). Reuses, rather than
reinvents, three things already built: ml/scoring/valuation_discount.py's
haircut engine (climate-adjusted property value), ml/scoring/insurance_pricing.py
via realestate_impact.py's noi_impact() (operating-income drag), and
ml/regulatory/eu_taxonomy_classifier.py (real Annex I citation for every
property, since 68.20 real estate is already mapped eligible).
"""
from __future__ import annotations

import io
import uuid
from collections import defaultdict
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
from ml.regulatory.eu_taxonomy_classifier import classify_taxonomy
from ml.scoring.realestate_impact import noi_impact
from services.calc_settings import get_calc_settings
from services.portfolio_engine import (
    apply_valuation_override as engine_apply_override,
    clear_valuation_override as engine_clear_override,
    fetch_entities_with_risk, get_entity_org, get_entity_with_risk,
)
from services.scoring.on_demand import process_new_cells
from services.templates.workbook import build_export_workbook, build_template_workbook

EXT_REALESTATE_COLUMNS = ["CAST(x.annual_noi_eur AS FLOAT) AS annual_noi_eur", "x.epc_rating"]


def _realestate_extra(row, headline, hz):
    # thread the driving peril + building attributes so the NOI drag is vulnerability-differentiated,
    # consistent with the property's collateral haircut (both now share the one damage core).
    attrs = {"construction_type": row.get("construction_type"), "year_built": row.get("year_built"),
             "number_of_stories": row.get("number_of_stories")}
    impact = noi_impact(row["headline_score"], row["primary_value_eur"], row["annual_noi_eur"],
                        hazard=headline["hazard"], attrs=attrs) if headline else None
    tax = classify_taxonomy(REALESTATE_NACE, headline_bucket=row["headline_bucket"], resilience_rating=None,
                             epc_rating=row.get("epc_rating"), minimum_safeguards_status=row.get("minimum_safeguards_status"))
    return {"noi_impact": impact, "taxonomy_status": tax["status"], "taxonomy_activity_ref": tax["activity_ref"],
            "taxonomy_reasoning": tax["reasoning"]}


def _map_property_row(row):
    """Shared-engine row -> the exact shape /portfolio, /summary, /disclosure
    have always returned."""
    return {
        "property_id": row["entity_id"], "property_name": row["entity_name"], "property_type": row["entity_type"],
        "country": row["country"], "region": row["region"], "lat": row["lat"], "lon": row["lon"],
        "h3_cell": row["h3_cell"], "property_value_eur": row["primary_value_eur"],
        "annual_noi_eur": row["annual_noi_eur"], "construction_type": row["construction_type"],
        "year_built": row["year_built"], "number_of_stories": row["number_of_stories"],
        "hazards": row["hazards"], "headline_score": row["headline_score"],
        "headline_bucket": row["headline_bucket"], "headline_hazard": row["headline_hazard"],
        "valuation": row["valuation"], "noi_impact": row["noi_impact"],
        "taxonomy_status": row["taxonomy_status"], "taxonomy_activity_ref": row["taxonomy_activity_ref"],
        "taxonomy_reasoning": row["taxonomy_reasoning"], "epc_rating": row["epc_rating"],
        "borrower_entity_id": row["borrower_entity_id"], "minimum_safeguards_status": row["minimum_safeguards_status"],
    }

router = APIRouter(prefix="/v1/realestate", tags=["Real Estate"])

DEMO_ORG = "33333333-3333-4333-8333-333333333333"  # Stellar Logistics REIT (demo)
REALESTATE_NACE = "68.20"  # every property IS real estate -- same NACE code, same Annex I §7.7
_bearer = HTTPBearer(auto_error=False)


def resolve_org(
    org_id: Optional[str] = Query(None),
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)] = None,
) -> str:
    """User JWT's org wins (tenant isolation); else query param; else the demo REIT."""
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


def _properties_with_risk(session, org_id, scenario, horizon, severity_model="universal",
                          entity_ids=None, value_weights=None):
    """All of an org's properties (metadata) + their per-hazard projected risk.
    Thin wrapper over the shared portfolio engine (services/portfolio_engine.py)."""
    rows = fetch_entities_with_risk(session, org_id, "realestate", scenario, horizon, severity_model,
                                     ext_table="ext_realestate", ext_columns=EXT_REALESTATE_COLUMNS,
                                     extra_calc=_realestate_extra,
                                     entity_ids=entity_ids, value_weights=value_weights)
    return [_map_property_row(r) for r in rows]


def _rollup(properties):
    total = sum(p["property_value_eur"] or 0 for p in properties)
    total_noi = sum(p["annual_noi_eur"] or 0 for p in properties)
    impacted = [p for p in properties if p["noi_impact"]]
    total_premium = sum(p["noi_impact"]["expected_insurance_premium_eur"] for p in impacted)
    total_discounted = sum(p["valuation"]["discounted_value_eur"] for p in properties)
    by_bucket = defaultdict(lambda: {"count": 0, "value_eur": 0.0})
    for p in properties:
        b = p["headline_bucket"] or "none"
        by_bucket[b]["count"] += 1
        by_bucket[b]["value_eur"] += p["property_value_eur"] or 0
    return {
        "n_properties": len(properties),
        "n_scored": sum(1 for p in properties if p["headline_bucket"]),
        "total_value_eur": round(total),
        "total_annual_noi_eur": round(total_noi),
        "total_discounted_value_eur": round(total_discounted),
        "total_expected_insurance_premium_eur": round(total_premium),
        "portfolio_noi_impact_pct": round(100 * total_premium / total_noi, 2) if total_noi else 0,
        "by_bucket": {k: {"count": v["count"], "value_eur": round(v["value_eur"])} for k, v in by_bucket.items()},
        "top_properties": sorted(
            [p for p in properties if p["headline_score"] is not None],
            key=lambda p: -p["headline_score"])[:8],
    }


@router.get("/portfolio", summary="Property book projected onto the golden source")
def portfolio(session: DbSession, org_id: OrgId,
              scenario: str = Query("baseline"), horizon: str = Query("current")):
    severity_model = get_calc_settings(session, org_id)["severity_model"]
    properties = _properties_with_risk(session, org_id, scenario, horizon, severity_model)
    return {"org_id": org_id, "scenario": scenario, "horizon": horizon,
            "rollup": _rollup(properties), "properties": properties}


@router.get("/forward-risk", summary="Forward-change decision signal — scenario risk migration + runway")
def forward_risk_ep(session: DbSession, org_id: OrgId, scenario: str = Query("disorderly_2c")):
    from services.intelligence.forward_risk import forward_risk
    return forward_risk(session, org_id, "realestate", scenario)


@router.get("/summary", summary="Portfolio & NOI impact rollup")
def summary(session: DbSession, org_id: OrgId,
            scenario: str = Query("baseline"), horizon: str = Query("current")):
    org = session.execute(text(
        "SELECT name, type, country FROM organizations WHERE org_id = :o"
    ), {"o": org_id}).mappings().first()
    severity_model = get_calc_settings(session, org_id)["severity_model"]
    properties = _properties_with_risk(session, org_id, scenario, horizon, severity_model)
    return {"org_id": org_id, "org": dict(org) if org else None, "rollup": _rollup(properties)}


def build_disclosure_snapshot(session, org_id, scenario, horizon, entity_ids=None, value_weights=None):
    """The single source of truth for a REIT TCFD / EU-Taxonomy physical-risk disclosure — live callers
    (GET /disclosure) and frozen callers (filing snapshots) both go through this so the numbers can't drift.
    entity_ids / value_weights scope + consolidation-weight the book (None = whole org)."""
    severity_model = get_calc_settings(session, org_id)["severity_model"]
    properties = _properties_with_risk(session, org_id, scenario, horizon, severity_model,
                                       entity_ids=entity_ids, value_weights=value_weights)
    hazards: dict = {}
    for p in properties:
        for hz in p["hazards"]:
            h = hazards.setdefault(hz["hazard"], {
                "exposed_value_eur": 0.0, "n_exposed": 0, "max_score": 0.0,
                "model_version": hz["model_version"], "scored_at": hz["scored_at"]})
            if hz["bucket"] in ("H", "VH"):
                h["exposed_value_eur"] += p["property_value_eur"] or 0
                h["n_exposed"] += 1
            h["max_score"] = max(h["max_score"], hz["score"])
    for h in hazards.values():
        h["exposed_value_eur"] = round(h["exposed_value_eur"])
        h["max_score"] = round(h["max_score"], 1)
    tax = defaultdict(lambda: {"count": 0, "value_eur": 0.0})
    for p in properties:
        tax[p["taxonomy_status"]]["count"] += 1
        tax[p["taxonomy_status"]]["value_eur"] += p["property_value_eur"] or 0
    return {
        "rollup": _rollup(properties), "properties": properties,
        "by_hazard": hazards,
        "taxonomy": {k: {"count": v["count"], "value_eur": round(v["value_eur"])} for k, v in tax.items()},
    }


@router.get("/disclosure", summary="Physical-risk exposure + EU Taxonomy status — the data GRESB's "
                                    "Resilience module and CSRD physical-risk disclosure ask for")
def disclosure(session: DbSession, org_id: OrgId,
               scenario: str = Query("baseline"), horizon: str = Query("current")):
    """Not a fabricated GRESB score -- GRESB's own survey criteria and scoring
    weights aren't something we've verified against a primary source, so this
    surfaces the real underlying data (exposure by hazard, taxonomy status)
    that a GRESB or CSRD submission would actually need, honestly labeled."""
    snap = build_disclosure_snapshot(session, org_id, scenario, horizon)
    return {"org_id": org_id, "scenario": scenario, "horizon": horizon,
            "rollup": snap["rollup"], "by_hazard": snap["by_hazard"], "taxonomy": snap["taxonomy"]}


# A property schedule -- ~80% the same shape as insurance's Statement of Values,
# already built (see services/templates/workbook.py). annual_noi_eur is required:
# without it, this vertical's headline NOI-impact figure can't be computed.
PROPERTY_TEMPLATE_FIELDS = [
    {"name": "property_name", "required": True, "description": "Free-text property name.", "example": "Rotterdam Logistics Park 4"},
    {"name": "latitude", "required": True, "description": "Decimal degrees.", "example": "51.9244"},
    {"name": "longitude", "required": True, "description": "Decimal degrees.", "example": "4.4777"},
    {"name": "property_value_eur", "required": True, "description": "Current market/appraised value.", "example": "42000000"},
    {"name": "annual_noi_eur", "required": True, "description": "Annual net operating income.", "example": "2400000"},
    {"name": "property_type", "required": True, "description": "office / retail / logistics / light_industrial / multifamily.", "example": "logistics"},
    {"name": "construction_type", "required": False, "description": "ISO Construction Class: frame / joisted_masonry / non_combustible / masonry_non_combustible / fire_resistive.", "example": "non_combustible"},
    {"name": "year_built", "required": False, "description": "Year of construction.", "example": "2011"},
    {"name": "number_of_stories", "required": False, "description": "Number of stories.", "example": "1"},
    {"name": "region", "required": False, "description": "Free-text region.", "example": "South Holland"},
    {"name": "country", "required": False, "description": "ISO-2 country code.", "example": "NL"},
    {"name": "epc_rating", "required": False, "description": "Building Energy Performance Certificate grade (A-G) — "
     "enables a real EU Taxonomy substantial-contribution check instead of an unverified gap.", "example": "B"},
    {"name": "borrower_entity_id", "required": False, "description": "Owning entity's LEI or other stable ID — "
     "lets a minimum-safeguards compliance flag be matched/refreshed by entity rather than re-collected per property.", "example": "5493001KJTIIGC8Y1R12"},
    {"name": "minimum_safeguards_status", "required": False, "description": "compliant / non_compliant, from your own "
     "OECD/UN/ILO counterparty screening — enables a real EU Taxonomy minimum-safeguards check.", "example": "compliant"},
]
REQUIRED_PROPERTY_COLUMNS = [f["name"] for f in PROPERTY_TEMPLATE_FIELDS if f["required"]]
CONSTRUCTION_TYPES = {"frame", "joisted_masonry", "non_combustible", "masonry_non_combustible", "fire_resistive"}
EPC_RATINGS = {"A", "B", "C", "D", "E", "F", "G"}
SAFEGUARDS_STATUSES = {"compliant", "non_compliant"}


@router.get("/property/{property_id}", summary="One property — full projection + provenance")
def property_detail(property_id: str, session: DbSession):
    org_id = get_entity_org(session, property_id)
    if not org_id:
        return {"error": "property not found"}
    severity_model = get_calc_settings(session, org_id)["severity_model"]
    row = get_entity_with_risk(session, property_id, "baseline", "current", severity_model,
                                ext_table="ext_realestate", ext_columns=EXT_REALESTATE_COLUMNS,
                                extra_calc=_realestate_extra)
    property_ = {
        "property_id": row["entity_id"], "org_id": row["org_id"], "property_name": row["entity_name"],
        "property_type": row["entity_type"], "country": row["country"], "region": row["region"],
        "lat": row["lat"], "lon": row["lon"], "h3_cell": row["h3_cell"],
        "property_value_eur": row["primary_value_eur"], "annual_noi_eur": row["annual_noi_eur"],
        "construction_type": row["construction_type"], "year_built": row["year_built"],
        "number_of_stories": row["number_of_stories"],
        "taxonomy_status": row["taxonomy_status"], "taxonomy_activity_ref": row["taxonomy_activity_ref"],
        "taxonomy_reasoning": row["taxonomy_reasoning"], "epc_rating": row["epc_rating"],
        "borrower_entity_id": row["borrower_entity_id"], "minimum_safeguards_status": row["minimum_safeguards_status"],
    }
    audit = session.execute(text("""
        SELECT actor_user_id::text AS actor_user_id, action, detail, created_at
        FROM access_audit_log WHERE target_type = 'realestate_property' AND target_id = :p
        ORDER BY created_at DESC LIMIT 5
    """), {"p": property_id}).mappings().all()
    return {
        "property": property_, "risks": row["risks"], "valuation": row["valuation"],
        "noi_impact": row["noi_impact"], "valuation_audit": [dict(x) for x in audit],
    }


class PropertyValuationOverrideRequest(BaseModel):
    discount_pct: float = Field(..., ge=0, le=100)
    reason: Optional[str] = None


@router.post("/property/{property_id}/valuation-override",
             summary="Override the recommended valuation discount (audited)")
def override_property_valuation(property_id: str, body: PropertyValuationOverrideRequest,
                                 session: DbSession, ctx: CurrentUser):
    if "pricing.approve" not in ctx["permissions"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Missing permission: pricing.approve"})
    org_id = get_entity_org(session, property_id)
    if not org_id:
        raise HTTPException(status_code=404, detail="property not found")
    if org_id != ctx["org"]["org_id"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Property does not belong to your organization"})

    result = engine_apply_override(session, property_id, body.discount_pct, ctx["user"]["id"], body.reason)
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="property.valuation.override", target_type="realestate_property", target_id=property_id,
                detail={"from_pct": result["from_pct"], "to_pct": body.discount_pct, "reason": body.reason})
    return {"property_id": property_id, "override_discount_pct": body.discount_pct,
            "overridden_at": result["overridden_at"].isoformat()}


@router.delete("/property/{property_id}/valuation-override",
               summary="Clear an override, revert to the recommended discount (audited)")
def clear_property_valuation_override(property_id: str, session: DbSession, ctx: CurrentUser):
    if "pricing.approve" not in ctx["permissions"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Missing permission: pricing.approve"})
    prior = engine_clear_override(session, property_id)
    if not prior:
        return {"property_id": property_id, "cleared": False}
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="property.valuation.override_cleared", target_type="realestate_property", target_id=property_id,
                detail={"from_pct": prior["override_discount_pct"], "to_pct": None})
    return {"property_id": property_id, "cleared": True}


@router.get("/properties/template.xlsx", summary="Download the property schedule upload template (Excel)")
def properties_template_xlsx():
    buf = build_template_workbook(PROPERTY_TEMPLATE_FIELDS)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              headers={"Content-Disposition": "attachment; filename=tellumen_property_schedule_template.xlsx"})


@router.post("/properties/upload", summary="Bulk-upload properties from a CSV into your portfolio")
async def upload_properties(session: DbSession, ctx: CurrentUser, file: UploadFile = File(...)):
    """Same shape as bank.py/insurance.py/supply.py's upload endpoints: lands in
    the uploader's OWN org, resolves an H3 cell per row, then processes new
    cells against the golden source via the shared process_new_cells."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")
    raw = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}")

    missing = [c for c in REQUIRED_PROPERTY_COLUMNS if c not in df.columns]
    if missing:
        raise HTTPException(status_code=400, detail={"error": "missing_columns", "missing": missing})

    org_id = ctx["org"]["org_id"]
    records, cell_coords = [], {}
    for _, row in df.iterrows():
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
            value_eur = float(row["property_value_eur"])
            noi_eur = float(row["annual_noi_eur"])
        except (TypeError, ValueError):
            continue  # a row with an unparsable required field is skipped, not fatal to the whole upload
        construction = str(row["construction_type"]).strip().lower() if "construction_type" in df.columns and pd.notna(row.get("construction_type")) else None
        if construction and construction not in CONSTRUCTION_TYPES:
            construction = None
        epc = str(row["epc_rating"]).strip().upper() if "epc_rating" in df.columns and pd.notna(row.get("epc_rating")) else None
        if epc and epc not in EPC_RATINGS:
            epc = None
        safeguards = str(row["minimum_safeguards_status"]).strip().lower() if "minimum_safeguards_status" in df.columns and pd.notna(row.get("minimum_safeguards_status")) else None
        if safeguards and safeguards not in SAFEGUARDS_STATUSES:
            safeguards = None
        cell = h3.latlng_to_cell(lat, lon, 8)
        cell_coords[cell] = (lat, lon)
        records.append({
            "entity_id": str(uuid.uuid4()), "org_id": org_id,
            "entity_name": str(row["property_name"]), "entity_type": str(row["property_type"]),
            "latitude": lat, "longitude": lon, "h3_cell": cell,
            "region": str(row["region"]) if "region" in df.columns and pd.notna(row.get("region")) else None,
            "country": str(row["country"]) if "country" in df.columns and pd.notna(row.get("country")) else None,
            "primary_value_eur": value_eur, "annual_noi_eur": noi_eur,
            "construction_type": construction,
            "year_built": int(row["year_built"]) if "year_built" in df.columns and pd.notna(row.get("year_built")) else None,
            "number_of_stories": int(row["number_of_stories"]) if "number_of_stories" in df.columns and pd.notna(row.get("number_of_stories")) else None,
            "epc_rating": epc,
            "borrower_entity_id": str(row["borrower_entity_id"]) if "borrower_entity_id" in df.columns and pd.notna(row.get("borrower_entity_id")) else None,
            "minimum_safeguards_status": safeguards,
        })
    if not records:
        raise HTTPException(status_code=400, detail="No valid rows found in the uploaded CSV")

    session.execute(text("""
        INSERT INTO portfolio_entities (entity_id, org_id, vertical, entity_name, entity_type,
                                         latitude, longitude, h3_cell, region, country,
                                         primary_value_eur, construction_type, year_built, number_of_stories,
                                         borrower_entity_id, minimum_safeguards_status)
        VALUES (:entity_id, :org_id, 'realestate', :entity_name, :entity_type,
                :latitude, :longitude, :h3_cell, :region, :country,
                :primary_value_eur, :construction_type, :year_built, :number_of_stories,
                :borrower_entity_id, :minimum_safeguards_status)
    """), records)
    session.execute(text("""
        INSERT INTO ext_realestate (entity_id, annual_noi_eur, epc_rating)
        VALUES (:entity_id, :annual_noi_eur, :epc_rating)
    """), records)
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="properties.upload",
                target_type="realestate_properties", target_id=None,
                detail={"n_rows": len(records), "filename": file.filename})

    processing = process_new_cells(cell_coords)
    return {"n_uploaded": len(records), **processing}


@router.get("/portfolio.xlsx", summary="Portfolio & NOI impact book (Excel)")
def portfolio_xlsx(session: DbSession, org_id: OrgId,
                    scenario: str = Query("baseline"), horizon: str = Query("current")):
    severity_model = get_calc_settings(session, org_id)["severity_model"]
    properties = _properties_with_risk(session, org_id, scenario, horizon, severity_model)
    headers = ["property_name", "property_type", "region", "country", "property_value_eur", "annual_noi_eur",
               "headline_hazard", "headline_score", "risk_bucket", "discounted_value_eur",
               "expected_insurance_premium_eur", "noi_impact_pct", "taxonomy_status"]
    rows = [[p["property_name"], p["property_type"], p["region"], p["country"], p["property_value_eur"],
             p["annual_noi_eur"], p["headline_hazard"], p["headline_score"], p["headline_bucket"] or "unscored",
             p["valuation"]["discounted_value_eur"],
             p["noi_impact"]["expected_insurance_premium_eur"] if p["noi_impact"] else None,
             p["noi_impact"]["noi_impact_pct"] if p["noi_impact"] else None,
             p["taxonomy_status"]] for p in properties]
    buf = build_export_workbook(headers, rows, sheet_name="Portfolio & NOI impact")
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              headers={"Content-Disposition": "attachment; filename=stellar-portfolio-noi-impact.xlsx"})
