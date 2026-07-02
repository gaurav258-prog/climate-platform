"""
Agriculture / supply-chain — public read-only endpoints for the COGS-at-risk workspace.

Projects the golden source (canonical_scores) onto a buyer's sourcing plots by H3 cell
(v_sc_plot_physical_risk), then runs the impact-function layer
(services/intelligence/supply_cogs) to roll a per-location hazard up the bill of materials
into a euro "COGS-at-risk". Mirrors bank.py: tenant-scoped, DEMO_ORG fallback, provenance kept.
Governance: unscored commodities (e.g. cocoa) return status='pending', € withheld.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from api.deps import DbSession
from services.intelligence.supply_cogs import project_org_supply, IMPACT_VERSION

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
    plots = session.execute(text("""
        SELECT p.plot_id::text AS plot_id, co.name AS commodity, p.plot_name, p.country, p.region,
               CAST(p.latitude AS FLOAT) AS lat, CAST(p.longitude AS FLOAT) AS lon, p.h3_cell,
               CAST(p.annual_spend_eur AS FLOAT) AS spend_eur, p.eudr_status
        FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id=p.commodity_id
        WHERE p.org_id=:o ORDER BY p.annual_spend_eur DESC
    """), {"o": org_id}).mappings().all()
    return {
        "org_id": org_id, "scenario": scenario, "horizon": horizon,
        "impact_version": IMPACT_VERSION,
        "commodities": [asdict(c) for c in r.commodities],
        "products": [dict(p) for p in products],
        "bom": [dict(b) for b in bom],
        "plots": [dict(p) for p in plots],
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
