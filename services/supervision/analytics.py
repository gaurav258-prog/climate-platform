"""Population analytics for the horizontal risk analyst — every figure an engine figure, precision labelled.

  concentration  — exposure by region (NUTS-3 / hexagon) and by headline hazard; concentration curve + top-10 share
  scenario_shift — value at high risk per scenario across the horizon anchors (projections carry a CMIP6 band
                   per hazard; here the band is the share of high-risk value whose headline hazard is banded)
  distribution   — the profile's metrics across entities: values, thresholds, population quartiles
Sector-agnostic: entities of every sector in the profile are pooled by value; the sector is kept on each point
so the page can split. Nothing is imputed: an entity with no located assets simply contributes nothing.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import text

from core.types import score_to_bucket
from services.geo.org_assets import org_asset_points
from services.geo.regions import aggregate_by_region
from services.supervision.benchmark import benchmark
from services.supervision.trend import anchor_coverage

SCENARIOS = ["baseline", "orderly_1_5c", "disorderly_2c", "hot_house_3_5c"]
HORIZONS = ["current", "2030", "2050", "2100"]
HIGH = {"H", "VH"}


def _high(p: dict) -> bool:
    return p.get("score") is not None and score_to_bucket(float(p["score"])).value in HIGH


def concentration(points: list[dict]) -> dict:
    total = sum(p["value_eur"] for p in points) or 0.0
    regions = aggregate_by_region([p for p in points if p.get("lat") is not None])
    by_region = sorted(({"key": r["key"], "name": r["name"], "country": r["country"], "kind": r["kind"], "value_eur": r["value_eur"],
                         "n_sites": r["n_sites"], "max_score": r["max_score"], "worst_hazard": r["worst_hazard"], "entities": r["entities"]}
                        for r in regions), key=lambda r: -r["value_eur"])
    cum, curve = 0.0, []
    for i, r in enumerate(by_region):
        cum += r["value_eur"]
        curve.append({"rank": i + 1, "cum_share_pct": round(100.0 * cum / total, 1) if total else 0})
    by_hazard: dict = defaultdict(lambda: {"value_eur": 0.0, "high_value_eur": 0.0, "n": 0})
    for p in points:
        h = by_hazard[p.get("hazard") or "unscored"]
        h["value_eur"] += p["value_eur"]; h["n"] += 1
        if _high(p):
            h["high_value_eur"] += p["value_eur"]
    hz = sorted(({"hazard": k, **{kk: (round(vv) if kk != "n" else vv) for kk, vv in v.items()}} for k, v in by_hazard.items()), key=lambda x: -x["value_eur"])
    unlocated = sum(p["value_eur"] for p in points if p.get("lat") is None)
    return {"total_value_eur": round(total), "unlocated_value_eur": round(unlocated), "n_regions": len(by_region),
            "top10_share_pct": (round(100.0 * sum(r["value_eur"] for r in by_region[:10]) / total, 1) if total else None),
            "by_region": by_region[:40], "curve": curve[:100], "by_hazard": hz}


def scenario_shift(session, entities: list[dict]) -> dict:
    """High-risk value per (scenario, horizon) for the population, plus the share of that value whose headline
    hazard is a CMIP6-projected one (flood / storm / wildfire) — the part that moves with the scenario.
    One grouped query over the population's cells: the headline is the worst standing hazard on the asset's cell
    at that anchor (nowcasts and scales that do not apply to the asset class excluded — the same rule the engine applies per asset); value = the asset's own
    exposure; unscored assets count in the total and never in the high-risk part."""
    from core.types import _BUCKET_THRESHOLDS, RiskBucket
    high_from = min(lo for lo, _, b in _BUCKET_THRESHOLDS if b in (RiskBucket.H, RiskBucket.VH))
    ids = [e["org_id"] for e in entities]
    cells = {}
    if ids:
        rows = session.execute(text("""
            WITH pop AS (
                -- each asset carries its class: built assets and operational sites read the buildings relevance,
                -- sourcing plots the agriculture relevance (core.hazard_relevance, mirrored in hazard_relevance)
                SELECT h3_cell, CAST(primary_value_eur AS FLOAT) AS value, 'buildings' AS cls FROM portfolio_entities
                WHERE org_id = ANY(CAST(:ids AS uuid[])) AND source = 'own'
                UNION ALL
                SELECT h3_cell, CAST(annual_value_eur AS FLOAT), 'buildings' FROM sc_company_sites WHERE org_id = ANY(CAST(:ids AS uuid[]))
                UNION ALL
                SELECT h3_cell, CAST(annual_spend_eur AS FLOAT), 'agriculture' FROM sc_sourcing_plots WHERE org_id = ANY(CAST(:ids AS uuid[]))
            ),
            anchors AS (SELECT DISTINCT scenario, time_horizon FROM canonical_scores WHERE score_lane = 'standing' AND valid_to IS NULL
                        AND scenario = ANY(CAST(:scs AS text[])) AND time_horizon = ANY(CAST(:hzs AS text[]))),
            scored AS (
                SELECT DISTINCT pc.h3_cell, pc.cls, c.scenario, c.time_horizon, c.hazard_type, CAST(c.risk_score AS FLOAT) AS score
                FROM (SELECT DISTINCT h3_cell, cls FROM pop WHERE h3_cell IS NOT NULL) pc
                JOIN canonical_scores c ON c.h3_cell = pc.h3_cell AND c.score_lane = 'standing' AND c.valid_to IS NULL
                LEFT JOIN hazard_relevance hr ON hr.hazard_type = c.hazard_type AND hr.asset_class = pc.cls
                WHERE COALESCE(hr.headline, TRUE)
            ),
            -- the engine's rule per asset: a hazard scored under the scenario uses its own row at the anchor; a hazard
            -- with NO row under that scenario (scenario-flat susceptibility layers) is carried flat from baseline/today
            per_anchor AS (
                SELECT a.scenario, a.time_horizon, s.h3_cell, s.cls, s.hazard_type, s.score
                FROM anchors a JOIN scored s ON s.scenario = a.scenario AND s.time_horizon = a.time_horizon
                UNION ALL
                SELECT a.scenario, a.time_horizon, b.h3_cell, b.cls, b.hazard_type, b.score
                FROM anchors a JOIN scored b ON b.scenario = 'baseline' AND b.time_horizon = 'current'
                WHERE a.scenario <> 'baseline'
                  AND NOT EXISTS (SELECT 1 FROM scored x WHERE x.h3_cell = b.h3_cell AND x.cls = b.cls AND x.hazard_type = b.hazard_type AND x.scenario = a.scenario)
            ),
            head AS (
                SELECT DISTINCT ON (scenario, time_horizon, h3_cell, cls) h3_cell, cls, scenario, time_horizon, score, hazard_type
                FROM per_anchor ORDER BY scenario, time_horizon, h3_cell, cls, score DESC
            )
            SELECT a.scenario, a.time_horizon,
                   (SELECT COALESCE(sum(value), 0) FROM pop) AS total,
                   COALESCE(sum(p.value) FILTER (WHERE h.score >= :hi), 0) AS high,
                   COALESCE(sum(p.value) FILTER (WHERE h.score >= :hi AND h.hazard_type = ANY(CAST(:proj AS text[]))), 0) AS high_proj
            FROM anchors a
            LEFT JOIN head h ON h.scenario = a.scenario AND h.time_horizon = a.time_horizon
            LEFT JOIN pop p ON p.h3_cell = h.h3_cell AND p.cls = h.cls
            GROUP BY a.scenario, a.time_horizon
        """), {"ids": ids, "scs": SCENARIOS, "hzs": HORIZONS, "hi": high_from,
               "proj": ["flood", "storm", "wildfire"]}).mappings().all()
        cells = {(r["scenario"], r["time_horizon"]): r for r in rows}
    out = []
    for sc in SCENARIOS:
        for hz in HORIZONS:
            r = cells.get((sc, hz))
            tot, high, high_proj = (float(r["total"]), float(r["high"]), float(r["high_proj"])) if r else (0.0, 0.0, 0.0)
            out.append({"scenario": sc, "horizon": hz, "value_eur": round(tot), "high_risk_value_eur": round(high),
                        "high_risk_share_pct": (round(100.0 * high / tot, 1) if tot else None),
                        "projected_share_of_high_pct": (round(100.0 * high_proj / high, 1) if high else None),
                        "scored": r is not None})
    return {"scenarios": SCENARIOS, "horizons": HORIZONS, "cells": out,
            "note": "Baseline and today reflect present-day hazard; the three scenario pathways apply local CMIP6 projected change "
                    "for flood, storm and wildfire, and each model's own scenario response for the remaining hazards"}


def distribution(session, cfg: dict, entities: list[dict], scenario: str, horizon: str) -> dict:
    b = benchmark(session, cfg, entities, scenario, horizon)
    out = {}
    for sec, s in b["sectors"].items():
        out[sec] = {"label": s["label"], "n_entities": s["n_entities"],
                    "metrics": [{k: v for k, v in m.items()} for m in s["metrics"]]}
    return out


def analytics(session, cfg: dict, entities: list[dict], scenario: str, horizon: str) -> dict:
    ents = [e for e in entities if e["type"] in cfg["sectors"]]
    points = []
    for e in ents:
        for p in org_asset_points(session, e["org_id"], scenario, horizon):
            p["entity"] = e["name"]; p["sector"] = e["type"]; points.append(p)
    return {"scenario": scenario, "horizon": horizon, "profile_id": cfg["profile_id"], "n_entities": len(ents), "n_assets": len(points),
            "precision": "Point-resolved (entity portfolios)",
            "concentration": concentration(points), "scenario_shift": scenario_shift(session, ents),
            "anchor_coverage": anchor_coverage(session, ents),
            "distribution": distribution(session, cfg, ents, scenario, horizon)}
