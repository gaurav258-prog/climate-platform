"""Read API (Export & Connect · Tier 2) — a documented, versioned, tenant-token-authenticated way for a
customer's OWN systems (Power BI / Tableau / a data warehouse) to PULL its authoritative Tellumen numbers on
a schedule, rather than screen-scrape or re-key.

Auth: the SAME tenant token the ingest API uses (Authorization: Bearer tlm_live_…) — org-scoped, revocable,
minted by an admin at POST /v1/ingest/tokens. So a service account that already pushes data in can also read
its results back out; nothing here is cross-tenant, and every figure is the same golden-source number the UI
shows. Reuses the shared engine + KRI services directly — no duplicated computation, no stored copies.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from api.deps import DbSession, IngestOrg

router = APIRouter(prefix="/v1/export", tags=["Read API (Export & Connect)"])

# org type → shared-engine vertical (the four financial books share one risk engine)
VERTICAL = {"bank": "banking", "asset_manager": "assetmgmt", "insurer": "insurance", "reit": "realestate"}
SCENARIOS = ["baseline", "orderly_1_5c", "disorderly_2c", "hot_house_3_5c"]
HORIZON_ANCHORS = ["current", "2030", "2050", "2100"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@router.get("/ping", summary="Verify a token and list the datasets this tenant can pull")
def ping(ctx: IngestOrg):
    sector = ctx["org_type"]
    datasets = ["metadata", "kri"]
    if sector in VERTICAL:
        datasets.insert(1, "book")
    return {
        "ok": True, "tenant": ctx["org_name"], "sector": sector,
        "datasets": datasets, "generated_at": _now(),
        "note": "Authoritative golden-source figures. Physical-risk (€ / score) is scenario × horizon; "
                "taxonomy & emissions are point-in-time book facts. Exploratory ≠ filed — a filed figure is "
                "the frozen, attested snapshot behind a submitted disclosure.",
    }


@router.get("/metadata", summary="Scenarios, horizons and KRI frameworks available to this tenant")
def metadata(session: DbSession, ctx: IngestOrg):
    from services.governance.kri import kri_frameworks
    return {
        "scenarios": SCENARIOS,
        "horizon_anchors": HORIZON_ANCHORS,
        "horizon_note": "Anchors are modelled; any year 2025–2100 is accepted and blended along the scenario's "
                        "global-warming-level curve (interpolated between the bracketing anchors).",
        "kri_frameworks": kri_frameworks(ctx["org_type"]),
        "generated_at": _now(),
    }


@router.get("/book", summary="The book with per-asset physical risk (financial sectors)")
def book(session: DbSession, ctx: IngestOrg,
         scenario: str = Query("disorderly_2c", description="One of the scenarios from /metadata."),
         horizon: str = Query("2050", description="A modelled anchor (current/2030/2050/2100) or any year 2025–2100.")):
    sector = ctx["org_type"]
    vertical = VERTICAL.get(sector)
    if not vertical:
        raise HTTPException(400, {"error": "unsupported_sector",
                                  "message": f"The book export is for financial books (bank / asset manager / insurer / REIT). "
                                             f"This tenant is '{sector}'."})
    if scenario not in SCENARIOS:
        raise HTTPException(400, {"error": "bad_scenario", "message": f"scenario must be one of {SCENARIOS}."})
    from services.portfolio_engine import fetch_entities_with_risk
    rows = fetch_entities_with_risk(session, ctx["org_id"], vertical, scenario, horizon)
    assets = [{
        "asset_id": r.get("entity_id"), "name": r.get("entity_name"), "type": r.get("entity_type"),
        "sector": r.get("sector"), "country": r.get("country"), "region": r.get("region"),
        "value_eur": r.get("primary_value_eur"),
        "headline_score": r.get("headline_score"), "headline_bucket": r.get("headline_bucket"),
        "headline_hazard": r.get("headline_hazard"),
        "hazards": r.get("hazards"),
    } for r in rows]
    total = sum(a["value_eur"] or 0 for a in assets)
    at_risk = [a for a in assets if a["headline_bucket"] in ("H", "VH")]
    return {
        "tenant": ctx["org_name"], "sector": sector, "scenario": scenario, "horizon": horizon,
        "generated_at": _now(),
        "rollup": {
            "n_assets": len(assets),
            "total_value_eur": round(total),
            "value_at_risk_eur": round(sum(a["value_eur"] or 0 for a in at_risk)),
            "n_at_risk": len(at_risk),
        },
        "assets": assets,
    }


@router.get("/kri", summary="Key-risk-indicator set for a framework (all sectors)")
def kri(session: DbSession, ctx: IngestOrg,
        framework: str = Query(None, description="A framework key from /metadata; defaults to the tenant's first.")):
    from services.governance.kri import kri as _kri
    from services.governance.kri import kri_frameworks
    fw = framework or (kri_frameworks(ctx["org_type"])[:1] or [{}])[0].get("framework")
    if not fw:
        raise HTTPException(400, {"error": "no_framework", "message": "No KRI framework available for this tenant."})
    data = _kri(session, ctx["org_id"], fw)
    return {"tenant": ctx["org_name"], "framework": fw, "generated_at": _now(), **data}
