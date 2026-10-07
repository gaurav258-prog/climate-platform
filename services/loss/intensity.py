"""Hazard intensity at asset locations (E171): each registered layer sampled once per location and layer version into
hazard_intensity_samples, through the isolated raster reader.

For the JRC river-flood layer, per return period:
  value          the depth at the point (m); a dry pixel reads 0, the depth at or below the layer's dry threshold too
  cell_fraction  the share of the location's H3 res-8 cell flooded (permanent water excluded)
  cell_mean      the mean depth over that flooded share
A location off every tile, or on a tile not held at all three return periods, is recorded 'outside_coverage' with no
value — never a zero.

The projected layer (WRI Aqueduct Floods) is sampled per map — its present day and each pathway × model × period — and
each sample names its scenario, period and climate model; today's layers carry 'present' / 'present' / ''."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.loss import registry

log = logging.getLogger(__name__)


def asset_points(session: Session) -> list[tuple[float, float]]:
    """Every distinct location of an asset or a company site."""
    rows = session.execute(text("""
        SELECT DISTINCT latitude, longitude FROM portfolio_entities WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        UNION
        SELECT DISTINCT latitude, longitude FROM sc_company_sites WHERE latitude IS NOT NULL AND longitude IS NOT NULL""")).all()
    return [(float(a), float(b)) for a, b in rows]


PRESENT = {"scenario": "present", "period": "present", "climate_model": ""}   # today's layers carry no projection


def _held(session: Session, key: str, version: str, variant: Optional[dict] = None) -> set[tuple[float, float]]:
    v = variant or PRESENT
    return {(float(a), float(b)) for a, b in session.execute(text("""
        SELECT DISTINCT latitude, longitude FROM hazard_intensity_samples WHERE layer_key = :k AND layer_version = :v
        AND scenario = :s AND period = :p AND climate_model = :m"""),
        {"k": key, "v": version, "s": v["scenario"], "p": v["period"], "m": v["climate_model"]}).all()}


def aqueduct_variants() -> list[dict]:
    """Every map of the registered Aqueduct layer: its present day, then each pathway × model × period."""
    L = registry.layer("aqueduct_river_flood")
    P = L["present"]
    out = [{"scenario": P["scenario"], "period": P["year"], "climate_model": P["model"]}]
    out += [{"scenario": s, "period": y, "climate_model": m} for s in L["pathways"] for m in L["models"] for y in L["periods"]]
    return out


def aqueduct_path(variant: dict, rp: int) -> Path:
    L = registry.layer("aqueduct_river_flood")
    return registry.ROOT / L["files"]["dir"] / L["files"]["pattern"].format(
        scenario=variant["scenario"], model=variant["climate_model"], year=variant["period"], rp=rp)


def aqueduct_rows(variant: dict, points: list[tuple[float, float]]) -> Optional[list[dict]]:
    """The rows of one Aqueduct map at many locations (no database): the 30″ pixel holding each location, read as the
    source reads it — wet when the depth exceeds 0 m (share 1, its depth as the mean), dry otherwise; no-data is dry.
    None when a file is missing or a read failed."""
    import h3

    from services.geo import raster_sampler
    L = registry.layer("aqueduct_river_flood")
    rows = []
    for rp in L["return_periods"]:
        path = aqueduct_path(variant, rp)
        if not path.exists():
            return None
        got = raster_sampler.sample(str(path), [(lon, lat) for lat, lon in points])
        if got is None:
            return None
        for (lat, lon), (v, *_rest) in zip(points, got):
            depth = 0.0 if (v != v or v <= L["dry_below"]) else float(v)
            wet = depth > L["dry_below"]
            rows.append({"layer_key": "aqueduct_river_flood", "layer_version": L["version"], "latitude": lat,
                         "longitude": lon, "h3_cell": h3.latlng_to_cell(lat, lon, 8), "rp_years": rp, "status": "sampled",
                         "value": depth, "cell_fraction": 1.0 if wet else 0.0, "cell_mean": depth if wet else 0.0, **variant})
    return rows


def sample_aqueduct(session: Session, points: Optional[Iterable[tuple[float, float]]] = None, chunk: int = 2000) -> dict:
    """Sample every Aqueduct map at every location it does not hold yet; commits per map and chunk."""
    L = registry.layer("aqueduct_river_flood")
    allp = list(points) if points is not None else asset_points(session)
    counts = {"maps": 0, "sampled": 0, "held": 0, "failed_maps": []}
    for v in aqueduct_variants():
        held = _held(session, "aqueduct_river_flood", L["version"], v)
        todo = [p for p in allp if p not in held]
        counts["held"] += len(held)
        for i in range(0, len(todo), chunk):
            rows = aqueduct_rows(v, todo[i:i + chunk])
            if rows is None:
                counts["failed_maps"].append(f"{v['scenario']}/{v['climate_model']}/{v['period']}")
                break
            _insert(session, rows)
            session.commit()
            counts["sampled"] += len(rows) // len(L["return_periods"])
        counts["maps"] += 1
        log.info("aqueduct %s %s %s: %d locations", v["scenario"], v["climate_model"], v["period"], len(todo))
    return counts


def jrc_flood_rows(lat: float, lon: float, tiles=None) -> list[dict]:
    """The rows for one location of the JRC river-flood layer (no database)."""
    import h3

    from ml.scoring import flood_jrc as F
    from services.geo import raster_sampler
    L = registry.layer("jrc_river_flood")
    cell = h3.latlng_to_cell(lat, lon, 8)
    base = {"layer_key": "jrc_river_flood", "layer_version": L["version"], "latitude": lat, "longitude": lon, "h3_cell": cell}
    name = F.tile_name(lat, lon)
    reader = F.TileReader(name) if name else None
    if reader is None or not reader.complete():
        return [{**base, "rp_years": rp, "status": "outside_coverage", "value": None, "cell_fraction": None, "cell_mean": None}
                for rp in L["return_periods"]]
    tiles = tiles or F.TileSet()
    stats = tiles.stats(F.cell_polygon(cell)) or {}
    out = []
    for rp in L["return_periods"]:
        got = raster_sampler.sample(reader.paths[rp], [(lon, lat)])
        if got is None:
            return []                    # a failed read: nothing recorded, the location is sampled again next run
        v = got[0][0]
        # the maps' encoding (ml.scoring.flood_jrc): dry land is NODATA (−9999), a value is a flooded pixel's depth
        depth = 0.0 if (v != v or v < 0 or v <= L["dry_below"]) else float(v)
        frac, mean, _mx = stats.get(rp, (None, None, None))
        out.append({**base, "rp_years": rp, "status": "sampled", "value": depth, "cell_fraction": frac, "cell_mean": mean})
    return out


def _storm_rows(lat: float, lon: float, _tiles=None) -> list[dict]:
    from services.loss import storm_events
    return storm_events.rows(lat, lon)


_SAMPLERS = {"jrc_river_flood": jrc_flood_rows, "storm_v4_wind": _storm_rows}


def sample(session: Session, layer_key: str, points: Optional[Iterable[tuple[float, float]]] = None,
           batch: int = 200) -> dict:
    """Sample a layer at every location not yet held for its version (all asset locations by default). Commits per
    batch. Returns {held, sampled, outside, failed}."""
    L = registry.layer(layer_key)
    if layer_key == "aqueduct_river_flood":
        return sample_aqueduct(session, points)
    if layer_key not in _SAMPLERS:
        raise registry.RegistryError(f"layer '{layer_key}' has no sampler yet")
    held = _held(session, layer_key, L["version"])
    todo = [p for p in (points if points is not None else asset_points(session)) if p not in held]
    counts = {"held": len(held), "sampled": 0, "outside": 0, "failed": 0}
    from ml.scoring import flood_jrc as F
    tiles = F.TileSet()
    rows: list[dict] = []
    for i, (lat, lon) in enumerate(todo, 1):
        got = _SAMPLERS[layer_key](lat, lon, tiles)
        if not got:
            counts["failed"] += 1
        elif got[0]["status"] == "outside_coverage":
            counts["outside"] += 1
        else:
            counts["sampled"] += 1
        rows.extend(got)
        if i % batch == 0 or i == len(todo):
            _insert(session, rows)
            session.commit()
            rows = []
            log.info("%s: %d of %d locations", layer_key, i, len(todo))
    return counts


def _insert(session: Session, rows: list[dict]) -> None:
    if rows:
        session.execute(text("""
            INSERT INTO hazard_intensity_samples (layer_key, layer_version, latitude, longitude, h3_cell, rp_years, status,
                                                  value, cell_fraction, cell_mean, scenario, period, climate_model)
            VALUES (:layer_key, :layer_version, :latitude, :longitude, :h3_cell, :rp_years, :status, :value,
                    :cell_fraction, :cell_mean, :scenario, :period, :climate_model)
            ON CONFLICT (layer_key, layer_version, latitude, longitude, rp_years, scenario, period, climate_model)
            DO NOTHING"""), [{**PRESENT, **r} for r in rows])


def sample_job(layer_key: str = "jrc_river_flood") -> dict:
    """The background job (services.tasks.jobs 'loss.sample_intensity'): its own session."""
    from core.db.session import get_session
    with get_session() as session:
        return sample(session, layer_key)
