"""Population-exposure prior: what a supervisory body's OWN supervised population says about a geography, weighted
by the sector's exposure measure (sum insured for an insurer, carrying amount for a bank — named by the profile).

The scored-land prior (geo_prior) gives every land cell one vote. An insurer's sum insured does not sit on land at
large, it sits on insured buildings; so for a sector whose profile asks for it, the reference is instead every
located point of every OTHER entity of that sector under this authority (the entity under review never judges
itself), each weighted by its exposure measure. Sensitive = headline High/Very high — the lens rule; the regional
unit is the same as the land prior (NUTS-3 in the EU, H3 res-4 elsewhere) so the two bands read alike.
Nothing is filled in: a point without the measure, or without a location, is excluded and counted.
"""
from __future__ import annotations

from typing import Optional

import h3

from core.types import score_to_bucket
from services.supervision.geo_prior import locate_cells, summarise
from services.supervision.lens import HIGH

SCORED_LAND, POPULATION = "scored_land", "population_exposure"
PRIOR_LABEL = {SCORED_LAND: "scored land, equal weight",
               POPULATION: "supervised population, weighted by the exposure measure"}


def weighted_rows(points: list[dict], measure_field: str = "value_eur") -> tuple[list[tuple], dict]:
    """Pure. points = [{country, region, lat, lon, score, hazard, <measure_field>}] with `region` already the regional
    key → (rows for summarise, exclusion counts). A point is excluded — and counted — when its measure is missing or
    non-positive, or it has no country/region. Sensitive = score bucket in High/Very high; unscored = not sensitive
    is NOT assumed: an unscored point is excluded too."""
    rows, n_missing, n_unlocated, n_unscored = [], 0, 0, 0
    for p in points:
        v = p.get(measure_field)
        try:
            w = float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            w = 0.0
        if w <= 0:
            n_missing += 1
            continue
        if not p.get("country") or not p.get("region"):
            n_unlocated += 1
            continue
        if p.get("score") is None:
            n_unscored += 1
            continue
        sens = score_to_bucket(float(p["score"])).value in HIGH
        rows.append((p["country"], p["region"], sens, p.get("hazard") or "unknown", w))
    return rows, {"n_points": len(points), "n_used": len(rows), "n_without_measure": n_missing,
                  "n_unlocated": n_unlocated, "n_unscored": n_unscored}


def _sector_entities(session, reg_org_id: str, sector_type: str, exclude_org_id: Optional[str]) -> list[str]:
    from sqlalchemy import text
    rows = session.execute(text("""SELECT o.org_id::text FROM supervision_scope sc JOIN organizations o ON o.org_id = sc.supervised_org_id
                                   WHERE sc.regulator_org_id = CAST(:r AS uuid) AND sc.active AND o.type = :t ORDER BY o.name"""),
                           {"r": reg_org_id, "t": sector_type}).scalars().all()
    return [r for r in rows if r != (exclude_org_id or "")]


def population_priors(session, reg_org_id: str, sector_type: str, scenario: str, horizon: str,
                      exclude_org_id: Optional[str] = None, measure_field: str = "value_eur") -> dict:
    """→ {"priors": {geo: prior}, "n_entities", counts…}. Points come from the same engine read the benchmark uses
    (services.geo.org_assets), so the prior and the peer benchmark agree to the euro."""
    from datetime import datetime, timezone

    from services.geo.org_assets import org_asset_points
    ents = _sector_entities(session, reg_org_id, sector_type, exclude_org_id)
    pts: list[dict] = []
    for org in ents:
        pts += org_asset_points(session, org, scenario, horizon)
    located = [p for p in pts if p.get("lat") is not None and p.get("lon") is not None]
    cells = [h3.latlng_to_cell(float(p["lat"]), float(p["lon"]), 8) for p in located]
    if cells:
        countries, regions = locate_cells(cells)
        for p, c, r in zip(located, countries, regions):
            p["country"], p["region"] = c, r
    for p in pts:
        if p.get("lat") is None or p.get("lon") is None:
            p["country"] = p["region"] = None
    rows, counts = weighted_rows(pts, measure_field)
    priors = summarise(rows)
    built = datetime.now(timezone.utc).isoformat()
    for p in priors.values():
        p["built_at"] = built
    return {"priors": priors, "n_entities": len(ents), "built_at": built, **counts}
