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

from core.types import score_to_bucket
from services.geo.org_assets import org_asset_points
from services.geo.regions import aggregate_by_region
from services.supervision.benchmark import benchmark

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
    hazard is a CMIP6-projected one (flood / storm / wildfire) — the part that moves with the scenario."""
    projected = {"flood", "storm", "wildfire"}
    out = []
    for sc in SCENARIOS:
        for hz in HORIZONS:
            tot = high = high_proj = 0.0
            for e in entities:
                for p in org_asset_points(session, e["org_id"], sc, hz):
                    tot += p["value_eur"]
                    if _high(p):
                        high += p["value_eur"]
                        if p.get("hazard") in projected:
                            high_proj += p["value_eur"]
            out.append({"scenario": sc, "horizon": hz, "value_eur": round(tot), "high_risk_value_eur": round(high),
                        "high_risk_share_pct": (round(100.0 * high / tot, 1) if tot else None),
                        "projected_share_of_high_pct": (round(100.0 * high_proj / high, 1) if high else None)})
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
            "distribution": distribution(session, cfg, ents, scenario, horizon)}
