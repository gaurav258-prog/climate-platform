"""
Banking flagship — public read-only endpoints for the loan-book workspace.

Projects the golden source (canonical_scores) onto a bank's assets by H3 cell,
the same projection as services/intelligence/asset_risk_projection and the
v_bank_asset_physical_risk view. Every figure carries its model_version + vintage
so the disclosure is defensible. No auth (aggregate read), mirroring platform.py.
"""
from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Query
from sqlalchemy import text

from api.deps import DbSession

router = APIRouter(prefix="/v1/bank", tags=["Banking"])

DEMO_ORG = "11111111-1111-4111-8111-111111111111"
BUCKET_RANK = {"VH": 4, "H": 3, "M": 2, "L": 1}


def _assets_with_risk(session, org_id, scenario, horizon):
    """All of an org's assets (metadata) + their per-hazard projected risk."""
    assets = session.execute(text("""
        SELECT asset_id::text AS asset_id, asset_name, asset_type, sector, country, region,
               CAST(latitude AS FLOAT) AS lat, CAST(longitude AS FLOAT) AS lon, h3_cell,
               CAST(asset_value_eur AS FLOAT) AS value_eur,
               CAST(annual_revenue_eur AS FLOAT) AS revenue_eur, taxonomy_status,
               construction_year, nace_code,
               CAST(ghg_emissions_scope1_tco2e AS FLOAT) AS ghg1,
               CAST(ghg_emissions_scope2_tco2e AS FLOAT) AS ghg2,
               CAST(ghg_emissions_scope3_tco2e AS FLOAT) AS ghg3
        FROM bank_assets WHERE org_id = :o ORDER BY asset_value_eur DESC
    """), {"o": org_id}).mappings().all()

    risks = session.execute(text("""
        SELECT asset_id::text AS asset_id, hazard_type,
               CAST(physical_risk_score AS FLOAT) AS score, risk_bucket,
               model_version, scored_at
        FROM v_bank_asset_physical_risk
        WHERE org_id = :o AND scenario = :s AND time_horizon = :h
    """), {"o": org_id, "s": scenario, "h": horizon}).mappings().all()

    by_asset = defaultdict(list)
    for r in risks:
        by_asset[r["asset_id"]].append({
            "hazard": r["hazard_type"], "score": round(r["score"], 1),
            "bucket": r["risk_bucket"], "model_version": r["model_version"],
            "scored_at": r["scored_at"],
        })

    out = []
    for a in assets:
        hz = sorted(by_asset.get(a["asset_id"], []), key=lambda x: -x["score"])
        headline = hz[0] if hz else None
        out.append({
            **{k: a[k] for k in a.keys()},
            "hazards": hz,
            "headline_score": headline["score"] if headline else None,
            "headline_bucket": headline["bucket"] if headline else None,
            "headline_hazard": headline["hazard"] if headline else None,
        })
    return out


def _rollup(assets):
    total = sum(a["value_eur"] or 0 for a in assets)
    at_risk = [a for a in assets if a["headline_bucket"] in ("H", "VH")]
    var = sum(a["value_eur"] or 0 for a in at_risk)
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
        "by_bucket": {k: {"count": v["count"], "value_eur": round(v["value"])} for k, v in by_bucket.items()},
        "top_assets": sorted(
            [a for a in assets if a["headline_score"] is not None],
            key=lambda a: -a["headline_score"])[:8],
    }


@router.get("/portfolio", summary="Loan book projected onto the golden source")
def portfolio(session: DbSession, org_id: str = Query(DEMO_ORG),
              scenario: str = Query("baseline"), horizon: str = Query("current")):
    assets = _assets_with_risk(session, org_id, scenario, horizon)
    return {"org_id": org_id, "scenario": scenario, "horizon": horizon,
            "rollup": _rollup(assets), "assets": assets}


@router.get("/summary", summary="Command-center rollup")
def summary(session: DbSession, org_id: str = Query(DEMO_ORG),
            scenario: str = Query("baseline"), horizon: str = Query("current")):
    org = session.execute(text(
        "SELECT name, type, country FROM organizations WHERE org_id = :o"
    ), {"o": org_id}).mappings().first()
    assets = _assets_with_risk(session, org_id, scenario, horizon)
    return {"org_id": org_id, "org": dict(org) if org else None, "rollup": _rollup(assets)}


@router.get("/disclosure", summary="TCFD / EU-Taxonomy disclosure pack from the projected book")
def disclosure(session: DbSession, org_id: str = Query(DEMO_ORG),
               scenario: str = Query("baseline"), horizon: str = Query("current")):
    assets = _assets_with_risk(session, org_id, scenario, horizon)
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
        "org_id": org_id, "scenario": scenario, "horizon": horizon,
        "rollup": _rollup(assets),
        "by_hazard": hazards,
        "taxonomy": {k: {"count": v["count"], "value_eur": round(v["value_eur"])} for k, v in tax.items()},
        "financed_emissions_tco2e": ghg,
    }


@router.get("/asset/{asset_id}", summary="One asset — full projection + provenance")
def asset_detail(asset_id: str, session: DbSession):
    a = session.execute(text("""
        SELECT asset_id::text AS asset_id, org_id::text AS org_id, asset_name, asset_type,
               sector, country, region, CAST(latitude AS FLOAT) AS lat,
               CAST(longitude AS FLOAT) AS lon, h3_cell,
               CAST(asset_value_eur AS FLOAT) AS value_eur,
               CAST(annual_revenue_eur AS FLOAT) AS revenue_eur, taxonomy_status,
               taxonomy_activity, construction_year, expected_lifespan_years, nace_code, gics_code,
               CAST(ghg_emissions_scope1_tco2e AS FLOAT) AS ghg_scope1,
               CAST(ghg_emissions_scope2_tco2e AS FLOAT) AS ghg_scope2,
               CAST(ghg_emissions_scope3_tco2e AS FLOAT) AS ghg_scope3
        FROM bank_assets WHERE asset_id = :a
    """), {"a": asset_id}).mappings().first()
    if not a:
        return {"error": "asset not found"}
    risks = session.execute(text("""
        SELECT hazard_type, scenario, time_horizon,
               CAST(physical_risk_score AS FLOAT) AS score, risk_bucket,
               model_version, scored_at, risk_source
        FROM v_bank_asset_physical_risk WHERE asset_id = :a
        ORDER BY hazard_type, scenario, time_horizon
    """), {"a": asset_id}).mappings().all()
    return {"asset": dict(a), "risks": [dict(r) for r in risks]}
