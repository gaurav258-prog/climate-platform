"""
Asset Management — public read-only endpoints for the Portfolio climate VaR
& screening workspace, the platform's 5th vertical.

Projects the golden source (canonical_scores) onto an asset manager's
holdings book via the shared portfolio engine (services/portfolio_engine.py)
and the unified v_portfolio_entity_physical_risk view -- the same engine
banking and real estate use (see the b9c0d1e2f3a4 migration). Needs ZERO new
scoring code: "climate VaR%" reuses
ml/scoring/valuation_discount.py's haircut-by-bucket schedule unchanged --
the same one banking uses for collateral and real estate uses for
climate-adjusted value -- and ml/regulatory/eu_taxonomy_classifier.py is
reused unchanged too. Nothing here is a new model, only a new label on two
functions three verticals now share.
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
from ml.scoring.valuation_discount import monte_carlo_var
from services.calc_settings import get_calc_settings
from services.portfolio_engine import (
    apply_valuation_override as engine_apply_override,
    clear_valuation_override as engine_clear_override,
    fetch_entities_with_risk, get_entity_org,
)
from services.scoring.on_demand import process_new_cells
from services.templates.workbook import build_export_workbook, build_template_workbook


def _assetmgmt_extra(row, headline, hz):
    bucket = row["headline_bucket"]
    tax = classify_taxonomy(row["nace_code"], headline_bucket=bucket, resilience_rating=None)
    return {"flagged": bucket in ("H", "VH"), "taxonomy_status": tax["status"],
            "taxonomy_activity_ref": tax["activity_ref"]}


def _map_holding_row(row):
    """Shared-engine row -> the exact shape /portfolio, /summary, /disclosure
    have always returned (note: this vertical calls it climate_var, not
    valuation -- same underlying valuation_block, different label)."""
    return {
        "holding_id": row["entity_id"], "holding_name": row["entity_name"], "sector": row["sector"],
        "nace_code": row["nace_code"], "country": row["country"], "region": row["region"],
        "lat": row["lat"], "lon": row["lon"], "h3_cell": row["h3_cell"],
        "position_value_eur": row["primary_value_eur"],
        "hazards": row["hazards"], "headline_score": row["headline_score"],
        "headline_bucket": row["headline_bucket"], "headline_hazard": row["headline_hazard"],
        "climate_var": row["valuation"], "flagged": row["flagged"],
        "taxonomy_status": row["taxonomy_status"], "taxonomy_activity_ref": row["taxonomy_activity_ref"],
    }

router = APIRouter(prefix="/v1/assetmgmt", tags=["Asset Management"])

DEMO_ORG = "44444444-4444-4444-8444-444444444444"  # Nordkap Asset Management (demo)
_bearer = HTTPBearer(auto_error=False)


def resolve_org(
    org_id: Optional[str] = Query(None),
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)] = None,
) -> str:
    """User JWT's org wins (tenant isolation); else query param; else the demo asset manager."""
    token = credentials.credentials if credentials else None
    if token and not token.startswith("cp_live_"):
        from api.security import decode_access_token
        payload = decode_access_token(token)
        if payload and payload.get("org_id"):
            return payload["org_id"]
    return org_id or DEMO_ORG


OrgId = Annotated[str, Depends(resolve_org)]


def _holdings_with_risk(session, org_id, scenario, horizon, severity_model="universal"):
    """All of an org's holdings (metadata) + their per-hazard projected risk.
    Thin wrapper over the shared portfolio engine (services/portfolio_engine.py) --
    asset management needs no extension table (sector/nace_code already live
    on the shared portfolio_entities table)."""
    rows = fetch_entities_with_risk(session, org_id, "assetmgmt", scenario, horizon, severity_model,
                                     extra_calc=_assetmgmt_extra)
    return [_map_holding_row(r) for r in rows]


def _rollup(holdings, var_method="haircut", org_id=None, scenario=None, horizon=None, severity_model="universal"):
    total = sum(h["position_value_eur"] or 0 for h in holdings)
    total_var = sum((h["position_value_eur"] or 0) - h["climate_var"]["discounted_value_eur"] for h in holdings)
    n_flagged = sum(1 for h in holdings if h["flagged"])
    by_bucket = defaultdict(lambda: {"count": 0, "value_eur": 0.0})
    for h in holdings:
        b = h["headline_bucket"] or "none"
        by_bucket[b]["count"] += 1
        by_bucket[b]["value_eur"] += h["position_value_eur"] or 0
    rollup = {
        "n_holdings": len(holdings),
        "n_scored": sum(1 for h in holdings if h["headline_bucket"]),
        "n_flagged": n_flagged,
        "total_portfolio_value_eur": round(total),
        "total_climate_var_eur": round(total_var),
        "portfolio_climate_var_pct": round(100 * total_var / total, 2) if total else 0,
        "by_bucket": {k: {"count": v["count"], "value_eur": round(v["value_eur"])} for k, v in by_bucket.items()},
        "top_holdings": sorted(
            [h for h in holdings if h["headline_score"] is not None],
            key=lambda h: -h["headline_score"])[:8],
        "var_method": var_method,
    }
    if var_method == "monte_carlo":
        scored = [{"position_value_eur": h["position_value_eur"], "bucket": h["headline_bucket"],
                   "hazard": h["headline_hazard"]} for h in holdings if h["headline_bucket"]]
        rollup["monte_carlo_var"] = monte_carlo_var(scored, org_id, scenario, horizon, severity_model)
    return rollup


@router.get("/portfolio", summary="Holdings book projected onto the golden source")
def portfolio(session: DbSession, org_id: OrgId,
              scenario: str = Query("baseline"), horizon: str = Query("current")):
    settings = get_calc_settings(session, org_id)
    holdings = _holdings_with_risk(session, org_id, scenario, horizon, settings["severity_model"])
    rollup = _rollup(holdings, settings["assetmgmt_var_method"], org_id, scenario, horizon, settings["severity_model"])
    return {"org_id": org_id, "scenario": scenario, "horizon": horizon,
            "rollup": rollup, "holdings": holdings}


@router.get("/summary", summary="Portfolio climate VaR rollup")
def summary(session: DbSession, org_id: OrgId,
            scenario: str = Query("baseline"), horizon: str = Query("current")):
    org = session.execute(text(
        "SELECT name, type, country FROM organizations WHERE org_id = :o"
    ), {"o": org_id}).mappings().first()
    settings = get_calc_settings(session, org_id)
    holdings = _holdings_with_risk(session, org_id, scenario, horizon, settings["severity_model"])
    rollup = _rollup(holdings, settings["assetmgmt_var_method"], org_id, scenario, horizon, settings["severity_model"])
    return {"org_id": org_id, "org": dict(org) if org else None, "rollup": rollup}


@router.get("/disclosure", summary="Physical-risk exposure + EU Taxonomy status — the portfolio-level "
                                    "metric TCFD's asset-owner/manager guidance recommends disclosing")
def disclosure(session: DbSession, org_id: OrgId,
               scenario: str = Query("baseline"), horizon: str = Query("current")):
    """TCFD's guidance for asset owners/managers recommends disclosing physical-risk
    exposure value-weighted across holdings -- this is that metric. NOT framed as
    an SFDR Principal Adverse Impact indicator: SFDR's mandatory PAI set has no
    direct physical-climate-risk metric (only fossil-fuel exposure/energy
    inefficiency for real estate holdings specifically, PAI 17/18)."""
    severity_model = get_calc_settings(session, org_id)["severity_model"]
    holdings = _holdings_with_risk(session, org_id, scenario, horizon, severity_model)
    hazards: dict = {}
    for h in holdings:
        for hz in h["hazards"]:
            entry = hazards.setdefault(hz["hazard"], {
                "exposed_value_eur": 0.0, "n_exposed": 0, "max_score": 0.0,
                "model_version": hz["model_version"], "scored_at": hz["scored_at"]})
            if hz["bucket"] in ("H", "VH"):
                entry["exposed_value_eur"] += h["position_value_eur"] or 0
                entry["n_exposed"] += 1
            entry["max_score"] = max(entry["max_score"], hz["score"])
    for entry in hazards.values():
        entry["exposed_value_eur"] = round(entry["exposed_value_eur"])
        entry["max_score"] = round(entry["max_score"], 1)
    tax = defaultdict(lambda: {"count": 0, "value_eur": 0.0})
    for h in holdings:
        tax[h["taxonomy_status"]]["count"] += 1
        tax[h["taxonomy_status"]]["value_eur"] += h["position_value_eur"] or 0
    return {
        "org_id": org_id, "scenario": scenario, "horizon": horizon,
        "rollup": _rollup(holdings),
        "by_hazard": hazards,
        "taxonomy": {k: {"count": v["count"], "value_eur": round(v["value_eur"])} for k, v in tax.items()},
    }


# Required fields keep an asset manager's actual holdings data recognizable
# (name, position size, sector); nace_code is optional but -- unlike banking's
# or real estate's upload today -- IS supported directly, since a manager's own
# data typically already carries a NACE classification.
HOLDING_TEMPLATE_FIELDS = [
    {"name": "holding_name", "required": True, "description": "Company / security name.", "example": "Nordisk Logistics Properties AB"},
    {"name": "latitude", "required": True, "description": "Decimal degrees (HQ or primary asset location).", "example": "59.3293"},
    {"name": "longitude", "required": True, "description": "Decimal degrees.", "example": "18.0686"},
    {"name": "position_value_eur", "required": True, "description": "Market value of the position.", "example": "18500000"},
    {"name": "sector", "required": True, "description": "Free-text sector / industry.", "example": "Real estate"},
    {"name": "nace_code", "required": False, "description": "NACE code, if known — enables real EU Taxonomy classification.", "example": "68.20"},
    {"name": "region", "required": False, "description": "Free-text region.", "example": "Stockholm"},
    {"name": "country", "required": False, "description": "ISO-2 country code.", "example": "SE"},
]
REQUIRED_HOLDING_COLUMNS = [f["name"] for f in HOLDING_TEMPLATE_FIELDS if f["required"]]


class HoldingValuationOverrideRequest(BaseModel):
    discount_pct: float = Field(..., ge=0, le=100)
    reason: Optional[str] = None


@router.post("/holding/{holding_id}/valuation-override",
             summary="Override the recommended climate-VaR discount (audited)")
def override_holding_valuation(holding_id: str, body: HoldingValuationOverrideRequest,
                                session: DbSession, ctx: CurrentUser):
    if "pricing.approve" not in ctx["permissions"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Missing permission: pricing.approve"})
    org_id = get_entity_org(session, holding_id)
    if not org_id:
        raise HTTPException(status_code=404, detail="holding not found")
    if org_id != ctx["org"]["org_id"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Holding does not belong to your organization"})

    result = engine_apply_override(session, holding_id, body.discount_pct, ctx["user"]["id"], body.reason)
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="holding.valuation.override", target_type="assetmgmt_holding", target_id=holding_id,
                detail={"from_pct": result["from_pct"], "to_pct": body.discount_pct, "reason": body.reason})
    return {"holding_id": holding_id, "override_discount_pct": body.discount_pct,
            "overridden_at": result["overridden_at"].isoformat()}


@router.delete("/holding/{holding_id}/valuation-override",
               summary="Clear an override, revert to the recommended discount (audited)")
def clear_holding_valuation_override(holding_id: str, session: DbSession, ctx: CurrentUser):
    if "pricing.approve" not in ctx["permissions"]:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Missing permission: pricing.approve"})
    prior = engine_clear_override(session, holding_id)
    if not prior:
        return {"holding_id": holding_id, "cleared": False}
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="holding.valuation.override_cleared", target_type="assetmgmt_holding", target_id=holding_id,
                detail={"from_pct": prior["override_discount_pct"], "to_pct": None})
    return {"holding_id": holding_id, "cleared": True}


@router.get("/holdings/template.xlsx", summary="Download the holdings book upload template (Excel)")
def holdings_template_xlsx():
    buf = build_template_workbook(HOLDING_TEMPLATE_FIELDS)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              headers={"Content-Disposition": "attachment; filename=tellumen_holdings_template.xlsx"})


@router.post("/holdings/upload", summary="Bulk-upload holdings from a CSV into your portfolio")
async def upload_holdings(session: DbSession, ctx: CurrentUser, file: UploadFile = File(...)):
    """Same shape as bank.py/insurance.py/supply.py/realestate.py's upload
    endpoints: lands in the uploader's OWN org, resolves an H3 cell per row,
    then processes new cells against the golden source via process_new_cells."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")
    raw = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}")

    missing = [c for c in REQUIRED_HOLDING_COLUMNS if c not in df.columns]
    if missing:
        raise HTTPException(status_code=400, detail={"error": "missing_columns", "missing": missing})

    org_id = ctx["org"]["org_id"]
    records, cell_coords = [], {}
    for _, row in df.iterrows():
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
            value_eur = float(row["position_value_eur"])
        except (TypeError, ValueError):
            continue  # a row with an unparsable required field is skipped, not fatal to the whole upload
        cell = h3.latlng_to_cell(lat, lon, 8)
        cell_coords[cell] = (lat, lon)
        records.append({
            "entity_id": str(uuid.uuid4()), "org_id": org_id,
            "entity_name": str(row["holding_name"]), "sector": str(row["sector"]),
            "nace_code": str(row["nace_code"]) if "nace_code" in df.columns and pd.notna(row.get("nace_code")) else None,
            "latitude": lat, "longitude": lon, "h3_cell": cell,
            "region": str(row["region"]) if "region" in df.columns and pd.notna(row.get("region")) else None,
            "country": str(row["country"]) if "country" in df.columns and pd.notna(row.get("country")) else None,
            "primary_value_eur": value_eur,
        })
    if not records:
        raise HTTPException(status_code=400, detail="No valid rows found in the uploaded CSV")

    session.execute(text("""
        INSERT INTO portfolio_entities (entity_id, org_id, vertical, entity_name, sector, nace_code,
                                         latitude, longitude, h3_cell, region, country, primary_value_eur)
        VALUES (:entity_id, :org_id, 'assetmgmt', :entity_name, :sector, :nace_code,
                :latitude, :longitude, :h3_cell, :region, :country, :primary_value_eur)
    """), records)
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="holdings.upload",
                target_type="assetmgmt_holdings", target_id=None,
                detail={"n_rows": len(records), "filename": file.filename})

    processing = process_new_cells(cell_coords)
    return {"n_uploaded": len(records), **processing}


@router.get("/portfolio.xlsx", summary="Portfolio climate VaR book (Excel)")
def portfolio_xlsx(session: DbSession, org_id: OrgId,
                    scenario: str = Query("baseline"), horizon: str = Query("current")):
    severity_model = get_calc_settings(session, org_id)["severity_model"]
    holdings = _holdings_with_risk(session, org_id, scenario, horizon, severity_model)
    headers = ["holding_name", "sector", "region", "country", "position_value_eur",
               "headline_hazard", "headline_score", "risk_bucket", "discounted_value_eur",
               "flagged", "taxonomy_status"]
    rows = [[h["holding_name"], h["sector"], h["region"], h["country"], h["position_value_eur"],
             h["headline_hazard"], h["headline_score"], h["headline_bucket"] or "unscored",
             h["climate_var"]["discounted_value_eur"], "yes" if h["flagged"] else "no",
             h["taxonomy_status"]] for h in holdings]
    buf = build_export_workbook(headers, rows, sheet_name="Portfolio climate VaR")
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              headers={"Content-Disposition": "attachment; filename=nordkap-portfolio-climate-var.xlsx"})
