"""Geography priors: what the platform's own hazard layers say about a geography, with no entity data at all.

For each basis (scenario × horizon) the standing canonical scores give every scored land cell a headline hazard
(max score across hazards, the same exclusions the lens uses). A cell is 'sensitive' when that headline sits in
High/Very high — the lens rule. Per geography we keep the share of sensitive cells and its spread across the
geography's regions (NUTS-3 in the EU, H3 res-4 elsewhere): a book concentrated in one region can sit anywhere
in that spread, so the spread — not the mean — is the plausibility band. 'EU' is the union of member states.
"""
from __future__ import annotations

import json
from typing import Optional

import h3
import numpy as np
from sqlalchemy import text

from core.types import score_to_bucket
from services.portfolio_engine import DEFAULT_HEADLINE_EXCLUDE
from services.supervision.lens import HIGH

MIN_CELLS_PER_REGION = 5
MIN_CELLS_PER_GEOGRAPHY = 30
SOURCE_NOTE = "Standing canonical scores per H3 res-8 cell; headline = max hazard score (heat_acute excluded); " \
              "sensitive = High/Very high; spread across NUTS-3 (EU, Eurostat GISCO 2021) or H3 res-4 regions."


def headline_by_cell(session, scenario: str, horizon: str) -> dict[str, tuple[float, str]]:
    rows = session.execute(text("""
        SELECT h3_cell, hazard_type, max(risk_score) AS score FROM canonical_scores
        WHERE score_lane = 'standing' AND valid_to IS NULL AND scenario = :sc AND time_horizon = :hz
          AND hazard_type <> ALL(CAST(:excl AS text[]))
        GROUP BY h3_cell, hazard_type
    """), {"sc": scenario, "hz": horizon, "excl": list(DEFAULT_HEADLINE_EXCLUDE)}).all()
    best: dict[str, tuple[float, str]] = {}
    for cell, hz, score in rows:
        if score is None:
            continue
        if cell not in best or float(score) > best[cell][0]:
            best[cell] = (float(score), hz)
    return best


def locate_cells(cells: list[str]) -> tuple[list[Optional[str]], list[str]]:
    """Country code and region key per cell, vectorised over the land and NUTS-3 trees."""
    from shapely.geometry import Point

    from services.geo.cells import _land
    from services.geo.regions import _index
    pts = [Point(*reversed(h3.cell_to_latlng(c))) for c in cells]
    countries: list[Optional[str]] = [None] * len(cells)
    land = _land()
    if land is not None:
        tree, geoms, codes = land
        for pi, gi in zip(*tree.query(pts, predicate="within")):
            if countries[int(pi)] is None:
                countries[int(pi)] = codes[int(gi)]
    regions: list[str] = [h3.cell_to_parent(c, 4) for c in cells]
    nuts = _index()
    if nuts is not None:
        tree, geoms, meta = nuts
        for pi, gi in zip(*tree.query(pts, predicate="within")):
            regions[int(pi)] = meta[int(gi)]["key"]
    return countries, regions


def summarise(rows: list[tuple[str, str, bool, str]]) -> dict[str, dict]:
    """rows = (country, region, sensitive, headline_hazard) → per-geography prior (countries + 'EU')."""
    from services.supervision.geo_prior_eu import EU_MEMBERS
    per_geo: dict[str, list] = {}
    for country, region, sens, hz in rows:
        if not country:
            continue
        per_geo.setdefault(country, []).append((region, sens, hz))
        if country in EU_MEMBERS:
            per_geo.setdefault("EU", []).append((region, sens, hz))
    out = {}
    for geo, items in per_geo.items():
        n = len(items)
        if n < MIN_CELLS_PER_GEOGRAPHY:
            continue
        by_region: dict[str, list[bool]] = {}
        mix: dict[str, int] = {}
        for region, sens, hz in items:
            by_region.setdefault(region, []).append(sens)
            if sens:
                mix[hz] = mix.get(hz, 0) + 1
        shares = np.array([np.mean(v) for v in by_region.values() if len(v) >= MIN_CELLS_PER_REGION])
        pct = (lambda q: float(np.percentile(shares, q))) if len(shares) >= 3 else (lambda q: None)
        out[geo] = {"n_cells": n, "share_sensitive": float(np.mean([s for _, s, _ in items])),
                    "p10": pct(10), "p25": pct(25), "p50": pct(50), "p75": pct(75), "p90": pct(90),
                    "n_regions": int(len(shares)),
                    "hazard_mix": dict(sorted(mix.items(), key=lambda kv: -kv[1])[:6])}
    return out


def build(session, scenario: str, horizon: str, loc_cache: Optional[dict] = None) -> int:
    """loc_cache: cell → (country, region), shared across bases so each cell is located once per run."""
    best = headline_by_cell(session, scenario, horizon)
    if not best:
        return 0
    cache = loc_cache if loc_cache is not None else {}
    missing = [c for c in best if c not in cache]
    if missing:
        countries, regions = locate_cells(missing)
        for i, c in enumerate(missing):
            cache[c] = (countries[i], regions[i])
    rows = [(cache[c][0], cache[c][1], score_to_bucket(best[c][0]).value in HIGH, best[c][1]) for c in best]
    priors = summarise(rows)
    for geo, p in priors.items():
        session.execute(text("""
            INSERT INTO supervision_geo_prior (geography, scenario, horizon, n_cells, share_sensitive, p10, p25, p50, p75, p90, n_regions, hazard_mix, source_note, built_at)
            VALUES (:g, :sc, :hz, :n, :s, :p10, :p25, :p50, :p75, :p90, :nr, CAST(:mix AS jsonb), :note, now())
            ON CONFLICT (geography, scenario, horizon) DO UPDATE SET n_cells = EXCLUDED.n_cells, share_sensitive = EXCLUDED.share_sensitive,
              p10 = EXCLUDED.p10, p25 = EXCLUDED.p25, p50 = EXCLUDED.p50, p75 = EXCLUDED.p75, p90 = EXCLUDED.p90,
              n_regions = EXCLUDED.n_regions, hazard_mix = EXCLUDED.hazard_mix, source_note = EXCLUDED.source_note, built_at = now()
        """), {"g": geo, "sc": scenario, "hz": horizon, "n": p["n_cells"], "s": p["share_sensitive"], "p10": p["p10"], "p25": p["p25"],
               "p50": p["p50"], "p75": p["p75"], "p90": p["p90"], "nr": p["n_regions"], "mix": json.dumps(p["hazard_mix"]), "note": SOURCE_NOTE})
    return len(priors)


def prior_for(session, geography: str, scenario: str, horizon: str) -> Optional[dict]:
    r = session.execute(text("""SELECT geography, scenario, horizon, n_cells, share_sensitive, p10, p25, p50, p75, p90, n_regions, hazard_mix, source_note, built_at
                                FROM supervision_geo_prior WHERE geography = :g AND scenario = :sc AND horizon = :hz"""),
                        {"g": (geography or "").strip().upper(), "sc": scenario, "hz": horizon}).mappings().first()
    if not r:
        return None
    d = dict(r); d["built_at"] = d["built_at"].isoformat()
    return d


def bases_available(session) -> list[tuple[str, str]]:
    return [tuple(r) for r in session.execute(text("SELECT DISTINCT scenario, horizon FROM supervision_geo_prior ORDER BY 1, 2")).all()]


def rebuild_all(only: Optional[list[str]] = None) -> dict:
    """Rebuild the priors for every basis with standing scores (the worker task and the script both call this)."""
    import time

    from core.db.session import get_session
    out = {}
    with get_session() as s:
        bases = [tuple(r) for r in s.execute(text("""SELECT DISTINCT scenario, time_horizon FROM canonical_scores
                                                     WHERE score_lane = 'standing' AND valid_to IS NULL ORDER BY 1, 2""")).all()]
        if only:
            bases = [b for b in bases if f"{b[0]}:{b[1]}" in only]
        cache: dict = {}
        for sc, hz in bases:
            t = time.time()
            out[f"{sc}:{hz}"] = {"geographies": build(s, sc, hz, cache), "seconds": round(time.time() - t, 1)}
            s.commit()
    return out
