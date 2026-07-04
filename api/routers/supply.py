"""
Agriculture / supply-chain — public read-only endpoints for the COGS-at-risk workspace.

Projects the golden source (canonical_scores) onto a buyer's sourcing plots by H3 cell
(v_sc_plot_physical_risk), then runs the impact-function layer
(services/intelligence/supply_cogs) to roll a per-location hazard up the bill of materials
into a euro "COGS-at-risk". Mirrors bank.py: tenant-scoped, DEMO_ORG fallback, provenance kept.
Governance: unscored commodities (e.g. cocoa) return status='pending', € withheld.
"""
from __future__ import annotations

import io
import uuid
from dataclasses import asdict
from typing import Annotated, Optional

import h3
import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from api.deps import CurrentUser, DbSession
from api.services.rbac import write_audit
from services.intelligence.supply_cogs import project_org_supply, IMPACT_VERSION
from services.scoring.on_demand import process_new_cells

router = APIRouter(prefix="/v1/supply", tags=["Agriculture / Supply chain"])

DEMO_ORG = "33333333-3333-4333-8333-333333333333"   # Terra Foods (demo)
_bearer = HTTPBearer(auto_error=False)


def resolve_org(
    org_id: Optional[str] = Query(None),
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)] = None,
) -> str:
    """User JWT's org wins (tenant isolation); else query param; else the demo CPG."""
    token = credentials.credentials if credentials else None
    if token and not token.startswith("cp_live_"):
        from api.security import decode_access_token
        payload = decode_access_token(token)
        if payload and payload.get("org_id"):
            return payload["org_id"]
    return org_id or DEMO_ORG


OrgId = Annotated[str, Depends(resolve_org)]


def _eudr_summary(session, org_id):
    rows = session.execute(text("""
        SELECT eudr_status, count(*) n FROM sc_sourcing_plots WHERE org_id=:o GROUP BY eudr_status
    """), {"o": org_id}).mappings().all()
    d = {r["eudr_status"]: r["n"] for r in rows}
    covered = session.execute(text("""
        SELECT DISTINCT co.name FROM sc_sourcing_plots p
        JOIN sc_commodities co ON co.commodity_id=p.commodity_id
        WHERE p.org_id=:o AND co.eudr_covered=true
    """), {"o": org_id}).scalars().all()
    return {"by_status": d, "covered_commodities": list(covered)}


@router.get("/summary", summary="Procurement book → COGS-at-risk rollup")
def summary(session: DbSession, org_id: OrgId,
            scenario: str = Query("baseline"), horizon: str = Query("current")):
    org = session.execute(text(
        "SELECT name, type, country FROM organizations WHERE org_id=:o"
    ), {"o": org_id}).mappings().first()
    r = project_org_supply(session, org_id, scenario=scenario, time_horizon=horizon)
    return {
        "org_id": org_id, "org": dict(org) if org else None,
        "scenario": scenario, "horizon": horizon, "impact_version": IMPACT_VERSION,
        "rollup": {
            "ingredient_spend_eur": r.ingredient_spend_eur, "total_cogs_eur": r.total_cogs_eur,
            "cogs_at_risk_p50_eur": r.cogs_at_risk_p50, "cogs_at_risk_p90_eur": r.cogs_at_risk_p90,
            "pct_cogs_at_risk": r.pct_cogs_at_risk, "n_commodities": r.n_commodities,
            "n_pending": r.n_pending,
        },
        "commodities": [asdict(c) for c in r.commodities],
        "eudr": _eudr_summary(session, org_id),
    }


@router.get("/portfolio", summary="Commodities + SKUs + plots")
def portfolio(session: DbSession, org_id: OrgId,
              scenario: str = Query("baseline"), horizon: str = Query("current")):
    r = project_org_supply(session, org_id, scenario=scenario, time_horizon=horizon)
    products = session.execute(text("""
        SELECT product_id::text AS product_id, name, category, annual_units,
               CAST(annual_revenue_eur AS FLOAT) AS revenue_eur,
               CAST(annual_cogs_eur AS FLOAT) AS cogs_eur
        FROM sc_products WHERE org_id=:o ORDER BY annual_cogs_eur DESC
    """), {"o": org_id}).mappings().all()
    bom = session.execute(text("""
        SELECT pr.product_id::text AS product_id, co.name AS commodity,
               CAST(b.cost_share_pct AS FLOAT) AS cost_share_pct,
               CAST(b.annual_spend_eur AS FLOAT) AS spend_eur
        FROM sc_bom_lines b JOIN sc_products pr ON pr.product_id=b.product_id
        JOIN sc_commodities co ON co.commodity_id=b.commodity_id
        WHERE pr.org_id=:o
    """), {"o": org_id}).mappings().all()
    # plots enriched with the worst projected hazard + bucket (for the map / sourcing book)
    from core.types import score_to_bucket
    plots = []
    for p in _plots_with_hazard(session, org_id, scenario, horizon):
        hs = p["hazard_score"]
        plots.append({**dict(p), "bucket": score_to_bucket(hs).value if hs is not None else None,
                      "hazard_score": round(hs, 1) if hs is not None else None})
    return {
        "org_id": org_id, "scenario": scenario, "horizon": horizon,
        "impact_version": IMPACT_VERSION,
        "commodities": [asdict(c) for c in r.commodities],
        "products": [dict(p) for p in products],
        "bom": [dict(b) for b in bom],
        "plots": plots,
    }


@router.get("/plot/{plot_id}", summary="One sourcing plot — projection + provenance")
def plot_detail(plot_id: str, session: DbSession):
    p = session.execute(text("""
        SELECT p.plot_id::text AS plot_id, p.org_id::text AS org_id, p.plot_name,
               co.name AS commodity, co.eudr_covered, s.name AS supplier, p.country, p.region,
               CAST(p.latitude AS FLOAT) AS lat, CAST(p.longitude AS FLOAT) AS lon, p.h3_cell,
               CAST(p.annual_spend_eur AS FLOAT) AS spend_eur,
               CAST(p.volume_share AS FLOAT) AS volume_share, p.eudr_status, p.eudr_geolocated_at
        FROM sc_sourcing_plots p
        JOIN sc_commodities co ON co.commodity_id=p.commodity_id
        LEFT JOIN sc_suppliers s ON s.supplier_id=p.supplier_id
        WHERE p.plot_id=:id
    """), {"id": plot_id}).mappings().first()
    if not p:
        return {"error": "plot not found"}
    risks = session.execute(text("""
        SELECT hazard_type, scenario, time_horizon,
               CAST(physical_risk_score AS FLOAT) AS score, model_version, scored_at
        FROM v_sc_plot_physical_risk WHERE plot_id=:id
        ORDER BY hazard_type, scenario, time_horizon
    """), {"id": plot_id}).mappings().all()
    return {"plot": dict(p), "impact_version": IMPACT_VERSION,
            "risks": [dict(r) for r in risks],
            "note": "€ impact is v0 (uncalibrated); see docs/SUPPLY_CHAIN_IMPACT_FUNCTION_METHODOLOGY.md"}


def _plots_with_hazard(session, org_id, scenario, horizon):
    """Each plot + its worst projected hazard + EUDR status (for map / disclosure / signals).
    Single DISTINCT ON pass (keeps the highest-scoring hazard per plot) — no per-plot subqueries."""
    rows = session.execute(text("""
        SELECT DISTINCT ON (p.plot_id)
               p.plot_id::text AS plot_id, co.name AS commodity, co.eudr_covered,
               p.plot_name, p.region, p.country, CAST(p.latitude AS FLOAT) AS lat,
               CAST(p.longitude AS FLOAT) AS lon, CAST(p.annual_spend_eur AS FLOAT) AS spend_eur,
               p.eudr_status, v.hazard_type AS top_hazard,
               CAST(v.physical_risk_score AS FLOAT) AS hazard_score
        FROM sc_sourcing_plots p
        JOIN sc_commodities co ON co.commodity_id = p.commodity_id
        LEFT JOIN v_sc_plot_physical_risk v
             ON v.plot_id = p.plot_id AND v.scenario = :s AND v.time_horizon = :h
        WHERE p.org_id = :o
        ORDER BY p.plot_id, v.physical_risk_score DESC NULLS LAST
    """), {"o": org_id, "s": scenario, "h": horizon}).mappings().all()
    return sorted(rows, key=lambda r: -(r["spend_eur"] or 0))


@router.get("/signals", summary="Early warning — commodities under elevated hazard now")
def signals(session: DbSession, org_id: OrgId,
            scenario: str = Query("baseline"), horizon: str = Query("current")):
    r = project_org_supply(session, org_id, scenario=scenario, time_horizon=horizon)
    def level(h):
        return "VH" if h >= 75 else "H" if h >= 55 else "M" if h >= 35 else "L"
    alerts = [{
        "commodity": c.commodity, "hazard": c.top_hazard, "avg_hazard": c.avg_hazard,
        "level": level(c.avg_hazard or 0), "spend_eur": c.annual_spend_eur,
        "cogs_at_risk_p50": c.cogs_at_risk_p50, "calibration": c.calibration,
    } for c in r.commodities if c.status == "scored" and (c.avg_hazard or 0) >= 55]
    alerts.sort(key=lambda a: -(a["avg_hazard"] or 0))
    pending = [{"commodity": c.commodity, "spend_eur": c.annual_spend_eur}
               for c in r.commodities if c.status == "pending"]
    return {"org_id": org_id, "scenario": scenario, "horizon": horizon,
            "n_alerts": len(alerts), "alerts": alerts, "pending": pending}


@router.get("/disclosure", summary="EUDR overlay + CSRD physical-risk pack from the book")
def disclosure(session: DbSession, org_id: OrgId,
               scenario: str = Query("baseline"), horizon: str = Query("current")):
    r = project_org_supply(session, org_id, scenario=scenario, time_horizon=horizon)
    plots = _plots_with_hazard(session, org_id, scenario, horizon)
    # EUDR overlay: deforestation-free AND climate-viable (hazard < 60)?
    eudr = []
    for p in plots:
        hs = p["hazard_score"]
        eudr.append({
            "commodity": p["commodity"], "plot": p["plot_name"], "region": p["region"],
            "country": p["country"], "eudr_covered": p["eudr_covered"],
            "eudr_status": p["eudr_status"], "hazard_score": round(hs, 1) if hs is not None else None,
            "climate_viable": (hs is not None and hs < 60),
            "scored": hs is not None,
        })
    covered = [e for e in eudr if e["eudr_covered"]]
    eudr_summary = {
        "covered_plots": len(covered),
        "deforestation_free": sum(1 for e in covered if e["eudr_status"] == "compliant"),
        "climate_at_risk": sum(1 for e in covered if e["scored"] and not e["climate_viable"]),
        "unscored": sum(1 for e in covered if not e["scored"]),
    }
    # CSRD physical-risk: COGS-at-risk by commodity × top hazard
    csrd = [{
        "commodity": c.commodity, "hazard": c.top_hazard, "avg_hazard": c.avg_hazard,
        "spend_eur": c.annual_spend_eur, "cogs_at_risk_p50": c.cogs_at_risk_p50,
        "cogs_at_risk_p90": c.cogs_at_risk_p90, "calibration": c.calibration, "status": c.status,
    } for c in r.commodities]
    return {
        "org_id": org_id, "scenario": scenario, "horizon": horizon, "impact_version": IMPACT_VERSION,
        "rollup": {"ingredient_spend_eur": r.ingredient_spend_eur, "total_cogs_eur": r.total_cogs_eur,
                   "cogs_at_risk_p50_eur": r.cogs_at_risk_p50, "cogs_at_risk_p90_eur": r.cogs_at_risk_p90,
                   "pct_cogs_at_risk": r.pct_cogs_at_risk},
        "csrd": csrd, "eudr": {"summary": eudr_summary, "plots": eudr},
    }


@router.get("/validation", summary="Impact-function backtests (the credibility record)")
def validation(session: DbSession):
    rows = session.execute(text("""
        SELECT event, commodity, hazard,
               CAST(observed_prod_shock_pct AS FLOAT) AS observed_prod_shock_pct,
               CAST(model_price_move_pct AS FLOAT) AS model_price_move_pct,
               CAST(observed_price_move_pct AS FLOAT) AS observed_price_move_pct,
               skill_note, source, run_at
        FROM sc_model_validation ORDER BY event
    """)).mappings().all()
    return {"impact_version": IMPACT_VERSION, "events": [dict(r) for r in rows]}


@router.get("/models", summary="Agriculture hazard models + impact-fn + per-commodity calibration")
def models(session: DbSession, org_id: OrgId):
    from services.intelligence.supply_cogs import COMMODITY_PARAMS, BACKTESTED, CROP_SENSITIVITY
    # ag hazard models (climatology-based) from the registry
    hz = session.execute(text("""
        SELECT hazard_type, model_version, algorithm, training_data_vintage, validation_note, is_active
        FROM model_registry
        WHERE hazard_type IN ('heat_acute','drought','frost') AND is_active = true
        ORDER BY hazard_type
    """)).mappings().all()
    # per-commodity calibration status for this org's book
    coms = session.execute(text("""
        SELECT DISTINCT co.name FROM sc_sourcing_plots p
        JOIN sc_commodities co ON co.commodity_id = p.commodity_id
        WHERE p.org_id = :o ORDER BY co.name
    """), {"o": org_id}).scalars().all()
    commodities = [{
        "commodity": c,
        "calibration": "backtested" if c in BACKTESTED else "indicative",
        "params": COMMODITY_PARAMS.get(c) or {"sensitivity": CROP_SENSITIVITY.get(c), "global_share": 1.0, "stock_to_use": None},
    } for c in coms]
    return {
        "impact_version": IMPACT_VERSION,
        "hazard_models": [dict(r) for r in hz],
        "commodities": commodities,
        "frost_note": "Frost hazard is built but not yet scored — CDS daily-min product is ECMWF-flagged unusable; pending fix.",
    }


REQUIRED_PLOT_COLUMNS = ["plot_name", "latitude", "longitude", "commodity", "annual_spend_eur"]


@router.post("/plots/upload", summary="Bulk-upload sourcing plots from a CSV into your procurement book")
async def upload_plots(session: DbSession, ctx: CurrentUser, file: UploadFile = File(...)):
    """Same shape as bank.py's assets/upload: lands in the uploader's OWN org,
    resolves an H3 cell per row, then processes new cells against the golden
    source via the shared services.scoring.on_demand.process_new_cells."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")
    raw = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}")

    missing = [c for c in REQUIRED_PLOT_COLUMNS if c not in df.columns]
    if missing:
        raise HTTPException(status_code=400, detail={"error": "missing_columns", "missing": missing})

    commodity_ids = {row["name"]: str(row["commodity_id"]) for row in
                     session.execute(text("SELECT commodity_id, name FROM sc_commodities")).mappings().all()}

    org_id = ctx["org"]["org_id"]
    records, cell_coords, unknown_commodities = [], {}, set()
    for _, row in df.iterrows():
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
            spend = float(row["annual_spend_eur"])
        except (TypeError, ValueError):
            continue
        commodity = str(row["commodity"])
        commodity_id = commodity_ids.get(commodity)
        if not commodity_id:
            unknown_commodities.add(commodity)
            continue
        cell = h3.latlng_to_cell(lat, lon, 8)
        cell_coords[cell] = (lat, lon)
        records.append({
            "plot_id": str(uuid.uuid4()), "org_id": org_id, "commodity_id": commodity_id,
            "plot_name": str(row["plot_name"]), "latitude": lat, "longitude": lon, "h3_cell": cell,
            "region": str(row["region"]) if "region" in df.columns and pd.notna(row.get("region")) else None,
            "country": str(row["country"]) if "country" in df.columns and pd.notna(row.get("country")) else None,
            "annual_spend_eur": spend,
        })
    if not records:
        raise HTTPException(status_code=400, detail={"error": "no_valid_rows", "unknown_commodities": list(unknown_commodities)})

    session.execute(text("""
        INSERT INTO sc_sourcing_plots (plot_id, org_id, commodity_id, plot_name, latitude, longitude,
                                        h3_cell, region, country, annual_spend_eur)
        VALUES (:plot_id, :org_id, :commodity_id, :plot_name, :latitude, :longitude,
                :h3_cell, :region, :country, :annual_spend_eur)
    """), records)
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="plots.upload",
                target_type="sc_sourcing_plots", target_id=None,
                detail={"n_rows": len(records), "filename": file.filename, "unknown_commodities": list(unknown_commodities)})

    processing = process_new_cells(cell_coords)
    return {"n_uploaded": len(records), "unknown_commodities": list(unknown_commodities), **processing}
