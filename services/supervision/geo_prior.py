"""Geography priors: what the platform's own hazard layers say about a geography, with no entity data at all.

For each basis (scenario × horizon) the standing canonical scores give every scored land cell a headline score
(max score across hazards, the same exclusions the lens uses). A cell is 'sensitive' when that headline is at or
above the at-risk level the comparison is made at — the level the entity stated for the template being judged, so
the prior and the submitted share mean the same thing (E69). The store therefore keeps, per geography and region
(NUTS-3 in the EU, H3 res-4 elsewhere), every cell's headline score (sorted, in hundredths — the canonical
precision) and hazard: the share at any stated level is an exact count at read time. A book concentrated in one
region can sit anywhere in the spread of regional shares, so the spread — not the mean — is the plausibility band.
'EU' is the union of member states.
"""
from __future__ import annotations

from typing import Optional

import h3
import numpy as np
from sqlalchemy import text

MIN_CELLS_PER_REGION = 5
MIN_CELLS_PER_GEOGRAPHY = 30
SOURCE_NOTE = "Standing canonical scores per H3 res-8 cell; headline = max hazard score over the scales that apply to built assets (nowcasts and crop-scale hazards excluded); " \
              "sensitive = headline at or above the stated at-risk level of the comparison; spread across NUTS-3 (EU, Eurostat GISCO 2021) or H3 res-4 regions."
HUNDREDTHS = 100          # headline scores are stored as integer hundredths (canonical_scores.risk_score is numeric(5,2))


def headline_by_cell(session, scenario: str, horizon: str) -> dict[str, tuple[float, str]]:
    rows = session.execute(text("""
        SELECT h3_cell, hazard_type, max(risk_score) AS score FROM canonical_scores
        WHERE score_lane = 'standing' AND valid_to IS NULL AND scenario = :sc AND time_horizon = :hz
          AND hazard_headline_eligible(hazard_type::text, 'buildings', model_version::text)
        GROUP BY h3_cell, hazard_type
    """), {"sc": scenario, "hz": horizon}).all()
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

    from services.geo.cells import _GEOS_LOCK, _land
    from services.geo.regions import _index

    pts = [Point(*reversed(h3.cell_to_latlng(c))) for c in cells]
    # Prepared geometries are not thread-safe: hold the shared lock for the whole vectorised query.
    with _GEOS_LOCK:
        return _locate_locked(cells, pts, _land(), _index())


def _locate_locked(cells, pts, land, nuts):
    countries: list[Optional[str]] = [None] * len(cells)
    if land is not None:
        tree, geoms, codes = land
        for pi, gi in zip(*tree.query(pts, predicate="within")):
            if countries[int(pi)] is None:
                countries[int(pi)] = codes[int(gi)]
    regions: list[str] = [h3.cell_to_parent(c, 4) for c in cells]
    if nuts is not None:
        tree, geoms, meta = nuts
        for pi, gi in zip(*tree.query(pts, predicate="within")):
            regions[int(pi)] = meta[int(gi)]["key"]
    return countries, regions


def _geo_rows(rows: list[tuple]) -> dict[str, list]:
    """rows = (country, region, score, hazard[, weight]) → per geography (countries + 'EU') its (region, score, hazard, w)."""
    from services.supervision.geo_prior_eu import EU_MEMBERS
    per_geo: dict[str, list] = {}
    for row in rows:
        country, region, score, hz = row[:4]
        w = float(row[4]) if len(row) > 4 else 1.0
        if not country or w <= 0 or score is None:
            continue
        per_geo.setdefault(country, []).append((region, float(score), hz, w))
        if country in EU_MEMBERS:
            per_geo.setdefault("EU", []).append((region, float(score), hz, w))
    return per_geo


def prior_at(items: list[tuple], level: float) -> dict | None:
    """Pure. items = (region, headline score, hazard, weight) of one geography → its prior at the stated level: the share
    sensitive (score ≥ level), the spread of that share across its regions (p10…p90) and the hazards of the sensitive
    cells. Without a weight every row counts once (scored land); with one, each row counts by its exposure measure
    (the population prior). None when the geography has too few cells to form a reference."""
    n = len(items)
    if n < MIN_CELLS_PER_GEOGRAPHY:
        return None
    by_region: dict[str, list[tuple[bool, float]]] = {}
    mix: dict[str, int] = {}
    for region, score, hz, w in items:
        sens = score >= level
        by_region.setdefault(region, []).append((sens, w))
        if sens:
            mix[hz] = mix.get(hz, 0) + 1
    wshare = lambda v: sum(w for s, w in v if s) / sum(w for _, w in v)  # noqa: E731
    shares = np.array([wshare(v) for v in by_region.values() if len(v) >= MIN_CELLS_PER_REGION])
    pct = (lambda q: float(np.percentile(shares, q))) if len(shares) >= 3 else (lambda q: None)
    return {"n_cells": n, "share_sensitive": float(wshare([(score >= level, w) for _, score, _, w in items])),
            "p10": pct(10), "p25": pct(25), "p50": pct(50), "p75": pct(75), "p90": pct(90),
            "n_regions": int(len(shares)), "at_risk_level": level,
            "hazard_mix": dict(sorted(mix.items(), key=lambda kv: -kv[1])[:6])}


def summarise(rows: list[tuple], level: float) -> dict[str, dict]:
    """rows = (country, region, headline score, hazard[, weight]) → per-geography prior at the stated level."""
    out = {}
    for geo, items in _geo_rows(rows).items():
        p = prior_at(items, level)
        if p is not None:
            out[geo] = p
    return out


def build(session, scenario: str, horizon: str, loc_cache: Optional[dict] = None) -> int:
    """Store every scored land cell's headline score and hazard, per geography and region, for one basis.
    loc_cache: cell → (country, region), shared across bases so each cell is located once per run."""
    best = headline_by_cell(session, scenario, horizon)
    if not best:
        return 0
    cache = loc_cache if loc_cache is not None else {}
    missing = [c for c in best if c not in cache]
    if missing:
        countries, regions = locate_cells(missing)
        for i, c in enumerate(missing):
            cache[c] = (countries[i], regions[i])
    per_geo = _geo_rows([(cache[c][0], cache[c][1], best[c][0], best[c][1]) for c in best])
    session.execute(text("DELETE FROM supervision_geo_prior_region WHERE scenario = :sc AND horizon = :hz"),
                    {"sc": scenario, "hz": horizon})
    n = 0
    for geo, items in per_geo.items():
        if len(items) < MIN_CELLS_PER_GEOGRAPHY:
            continue
        n += 1
        by_region: dict[str, list] = {}
        for region, score, hz, _ in items:
            by_region.setdefault(region, []).append((round(score * HUNDREDTHS), hz))
        for region, vals in by_region.items():
            vals.sort()
            session.execute(text("""
                INSERT INTO supervision_geo_prior_region (geography, scenario, horizon, region, scores, hazards, source_note, built_at)
                VALUES (:g, :sc, :hz, :r, CAST(:s AS smallint[]), CAST(:h AS text[]), :note, now())
            """), {"g": geo, "sc": scenario, "hz": horizon, "r": region, "s": [v for v, _ in vals],
                   "h": [h for _, h in vals], "note": SOURCE_NOTE})
    return n


def prior_for(session, geography: str, scenario: str, horizon: str, level: float) -> Optional[dict]:
    """The geography's prior at the stated level, read exactly from the stored regional scores."""
    rows = session.execute(text("""SELECT region, scores, hazards, built_at FROM supervision_geo_prior_region
                                   WHERE geography = :g AND scenario = :sc AND horizon = :hz"""),
                           {"g": (geography or "").strip().upper(), "sc": scenario, "hz": horizon}).all()
    if not rows:
        return None
    items = [(region, v / HUNDREDTHS, hz, 1.0) for region, scores, hazards, _ in rows for v, hz in zip(scores, hazards)]
    p = prior_at(items, level)
    if p is None:
        return None
    return {"geography": (geography or "").strip().upper(), "scenario": scenario, "horizon": horizon, **p,
            "source_note": SOURCE_NOTE, "built_at": max(r[3] for r in rows).isoformat()}


def bases_available(session) -> list[tuple[str, str]]:
    return [tuple(r) for r in session.execute(text("SELECT DISTINCT scenario, horizon FROM supervision_geo_prior_region ORDER BY 1, 2")).all()]


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
