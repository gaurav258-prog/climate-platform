"""Benchmark metric adapters — sector-agnostic computations over an entity's located book.

Each adapter id named in supervision_profiles.json (`adapter`) maps to one function of the entity's asset
points (services/geo/org_assets.org_asset_points — the same cross-sector reader the maps use), so a metric means
the same thing for a bank's financed assets, an insurer's locations, a fund's holdings, a REIT's properties or an
operator's sites. "High risk" is the platform's own bucket rule (core.types.score_to_bucket: High / Very high),
the one every sector page already shows — so the supervisor's number equals the entity's number.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable

from core.types import score_to_bucket

HIGH = {"H", "VH"}


def _is_high(p: dict) -> bool:
    return p.get("score") is not None and score_to_bucket(float(p["score"])).value in HIGH


def book_value(points: list[dict]) -> float:
    return round(sum(float(p.get("value_eur") or 0) for p in points))


def high_risk_value(points: list[dict]) -> float:
    return round(sum(float(p.get("value_eur") or 0) for p in points if _is_high(p)))


def high_risk_share(points: list[dict]) -> float | None:
    bv = book_value(points)
    return round(100.0 * high_risk_value(points) / bv, 1) if bv else None


def scored_share(points: list[dict]) -> float | None:
    return round(100.0 * sum(1 for p in points if p.get("score") is not None) / len(points), 1) if points else None


def _top_share(points: list[dict], key: Callable[[dict], str | None]) -> float | None:
    bv = book_value(points)
    if not bv:
        return None
    tot: dict[str, float] = defaultdict(float)
    for p in points:
        k = key(p)
        if k:
            tot[k] += float(p.get("value_eur") or 0)
    return round(100.0 * max(tot.values()) / bv, 1) if tot else None


def top_hazard_share(points: list[dict]) -> float | None:
    """Share of book whose headline hazard is the single most common one — concentration in one peril."""
    return _top_share(points, lambda p: p.get("hazard"))


def top_region_share(points: list[dict]) -> float | None:
    """Share of book in the single largest region (NUTS-3 / hexagon) — geographic concentration."""
    from services.geo.regions import region_for
    return _top_share(points, lambda p: region_for(p["lat"], p["lon"])["key"] if p.get("lat") is not None else None)


ADAPTERS: dict[str, Callable[[list[dict]], float | None]] = {
    "portfolio.book_value": book_value,
    "portfolio.high_risk_value": high_risk_value,
    "portfolio.high_risk_share": high_risk_share,
    "portfolio.top_hazard_share": top_hazard_share,
    "portfolio.top_region_share": top_region_share,
    "portfolio.scored_share": scored_share,
}


def compute(metric_specs: list[dict], points: list[dict]) -> dict[str, float | None]:
    """{metric_id: value} for every metric in a sector's spec; an unknown adapter is an error, not a silent None."""
    out = {}
    for m in metric_specs:
        fn = ADAPTERS.get(m["adapter"])
        if fn is None:
            raise KeyError(f"no adapter registered for {m['adapter']!r} (metric {m['id']})")
        out[m["id"]] = fn(points)
    return out


def flag(metric: dict, value: float | None) -> str:
    """'act' | 'watch' | 'ok' | 'na' against the (overridable) supervisory-expectation thresholds of the spec."""
    if value is None:
        return "na"
    if "act_above" in metric and value > metric["act_above"]:
        return "act"
    if "watch_above" in metric and value > metric["watch_above"]:
        return "watch"
    if "watch_below" in metric and value < metric["watch_below"]:
        return "watch"
    return "ok"
