"""Hazard intensity at asset locations (E171): each registered layer sampled once per location and layer version into
hazard_intensity_samples, through the isolated raster reader.

For the JRC river-flood layers (global, and the European maps with nine return periods), per return period:
  value          the depth at the point (m); a dry pixel reads 0, the depth at or below the layer's dry threshold too
  cell_fraction  the share of the location's H3 res-8 cell flooded (permanent water excluded)
  cell_mean      the mean depth over that flooded share
A location off every tile, or on a tile not held at all three return periods, is recorded 'outside_coverage' with no
value — never a zero.

A projection source (services.loss.projection.SOURCES) is sampled per map — its present day (unless another layer holds
it) and each pathway × period × member — and each sample names its scenario, period and member in climate_model: a
climate model (river flood, tropical cyclone) or a sea-level-rise percentile (coastal flood: p05, p50, p95). The WRI
Aqueduct maps (river and coastal) are read as the source reads them: the 30″ pixel holding the location. Today's layers
carry 'present' / 'present' / '' — the coastal maps' present day too, which serves today's coastal figure."""
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


def asset_points_in(session: Session, countries: Iterable[str]) -> list[tuple[float, float]]:
    """Every distinct location of an asset or a company site whose stated country is one of `countries` — for a layer
    that serves only those (registry.coverage_countries)."""
    rows = session.execute(text("""
        SELECT DISTINCT latitude, longitude FROM portfolio_entities
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL AND upper(trim(country)) = ANY(:c)
        UNION
        SELECT DISTINCT latitude, longitude FROM sc_company_sites
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL AND upper(trim(country)) = ANY(:c)"""),
        {"c": sorted(countries)}).all()
    return [(float(a), float(b)) for a, b in rows]


PRESENT = {"scenario": "present", "period": "present", "climate_model": ""}   # today's layers carry no projection


def _held(session: Session, key: str, version: str, variant: Optional[dict] = None) -> set[tuple[float, float]]:
    v = variant or PRESENT
    return {(float(a), float(b)) for a, b in session.execute(text("""
        SELECT DISTINCT latitude, longitude FROM hazard_intensity_samples WHERE layer_key = :k AND layer_version = :v
        AND scenario = :s AND period = :p AND climate_model = :m"""),
        {"k": key, "v": version, "s": v["scenario"], "p": v["period"], "m": v["climate_model"]}).all()}


def map_path(key: str, variant: dict, rp: int) -> Path:
    """The file of one map of a WRI Aqueduct layer: river maps by scenario, model and year; coastal maps by scenario,
    year and sea-level-rise percentile (the layer's members name each percentile's file suffix)."""
    from services.loss.projection import present_variant
    L = registry.layer(key)
    f = L["files"]
    if "{projection}" not in f["pattern"]:
        name = f["pattern"].format(scenario=variant["scenario"], model=variant["climate_model"], year=variant["period"],
                                   rp=rp)
    elif variant == present_variant(L):
        name = f["pattern"].format(**L["present"]["file"], rp=rp)
    else:
        name = f["pattern"].format(scenario=variant["scenario"], year=variant["period"], rp=rp,
                                   projection=L["members"][variant["climate_model"]])
    return registry.ROOT / f["dir"] / name


def map_rows(key: str, variant: dict, points: list[tuple[float, float]]) -> Optional[list[dict]]:
    """The rows of one Aqueduct map at many locations (no database): the 30″ pixel holding each location, read as the
    source reads it — wet when the depth exceeds 0 m (share 1, its depth as the mean), dry otherwise. No-data reads as
    the layer declares (no_data): outside the map (the coastal maps' sea), else dry (the river maps). None when a file is
    missing or a read failed."""
    import h3

    from services.geo import raster_sampler
    L = registry.layer(key)
    rows = []
    for rp in L["return_periods"]:
        path = map_path(key, variant, rp)
        if not path.exists():
            return None
        got = raster_sampler.sample(str(path), [(lon, lat) for lat, lon in points])
        if got is None:
            return None
        nd = L.get("no_data") or {}
        for (lat, lon), (v, *_rest) in zip(points, got):
            base = {"layer_key": key, "layer_version": L["version"], "latitude": lat, "longitude": lon,
                    "h3_cell": h3.latlng_to_cell(lat, lon, 8), "rp_years": rp, **variant}
            if nd.get("reads_as") == "outside" and (v != v or v == nd["value"]):      # the sea: no value, never a zero
                rows.append({**base, "status": "outside_coverage", "value": None, "cell_fraction": None, "cell_mean": None})
                continue
            depth = 0.0 if (v != v or v <= L["dry_below"]) else float(v)
            wet = depth > L["dry_below"]
            rows.append({**base, "status": "sampled", "value": depth, "cell_fraction": 1.0 if wet else 0.0,
                         "cell_mean": depth if wet else 0.0})
    return rows


def _rows_of(key: str, variant: dict, points: list[tuple[float, float]]) -> Optional[list[dict]]:
    if registry.layer(key).get("derived_from"):          # a wind layer derived from an event set (the STORM future set)
        from services.loss import storm_events
        return storm_events.member_rows(key, variant, points)
    return map_rows(key, variant, points)


def sample_maps(session: Session, key: str, variants: list[dict],
                points: Optional[Iterable[tuple[float, float]]] = None, chunk: int = 2000) -> dict:
    """Sample the given maps of a projection source at every location it does not hold yet; commits per map and chunk."""
    L = registry.layer(key)
    allp = list(points) if points is not None else asset_points(session)
    counts = {"maps": 0, "sampled": 0, "held": 0, "failed_maps": []}
    for v in variants:
        held = _held(session, key, L["version"], v)
        todo = [p for p in allp if p not in held]
        counts["held"] += len(held)
        for i in range(0, len(todo), chunk):
            rows = _rows_of(key, v, todo[i:i + chunk])
            if rows is None:
                counts["failed_maps"].append(f"{v['scenario']}/{v['climate_model']}/{v['period']}")
                break
            _insert(session, rows)
            session.commit()
            counts["sampled"] += len(rows) // len(L["return_periods"])
        counts["maps"] += 1
        log.info("%s %s %s %s: %d locations", key, v["scenario"], v["climate_model"], v["period"], len(todo))
    return counts


def sample_projection(session: Session, key: str, points: Optional[Iterable[tuple[float, float]]] = None) -> dict:
    """Every map of a projection source (services.loss.projection.variants)."""
    from services.loss.projection import variants
    return sample_maps(session, key, variants(key), points)


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


def jrc_europe_rows(lat: float, lon: float, _tiles=None) -> list[dict]:
    """The rows for one location of the JRC European river-flood maps (no database): per return period, the point's
    depth and the location's H3 res-8 cell statistics — read as the global maps are (permanent water excluded, depths at
    or below the dry threshold dry) — and the publisher's caution where its spurious-depth mask touches the cell. Off the
    maps: 'outside_coverage'. A failed read records nothing (the location is sampled again next run)."""
    import h3

    from ml.scoring.flood_jrc import cell_polygon
    from services.geo import raster_sampler
    L = registry.layer("jrc_river_flood_europe")
    d = registry.ROOT / L["files"]["dir"]
    cell = h3.latlng_to_cell(lat, lon, 8)
    ring = list(cell_polygon(cell).exterior.coords)
    base = {"layer_key": "jrc_river_flood_europe", "layer_version": L["version"], "latitude": lat, "longitude": lon,
            "h3_cell": cell}
    flagged = raster_sampler.zonal(str(d / L["files"]["caution"]), ring, above=0.5)
    if flagged is None:
        return [{**base, "rp_years": rp, "status": "outside_coverage", "value": None, "cell_fraction": None,
                 "cell_mean": None} for rp in L["return_periods"]]
    caution = L["caution"] if flagged["present"] else None
    water = {"path": str(d / L["files"]["water"]), "value": 1}
    out = []
    for rp in L["return_periods"]:
        path = str(d / L["files"]["pattern"].format(rp=rp))
        z = raster_sampler.zonal(path, ring, above=L["dry_below"], exclude=water)
        got = raster_sampler.sample(path, [(lon, lat)])
        if z is None or got is None:
            return []
        v = got[0][0]
        depth = 0.0 if (v != v or v < 0 or v <= L["dry_below"]) else float(v)
        frac = z["present"] / z["inside"] if z["inside"] else None
        mean = (z["sum"] / z["present"] if z["present"] else 0.0) if z["inside"] else None
        out.append({**base, "rp_years": rp, "status": "sampled", "value": depth, "cell_fraction": frac,
                    "cell_mean": mean, "caution": caution})
    return out


def _storm_rows(lat: float, lon: float, _tiles=None) -> list[dict]:
    from services.loss import storm_events
    return storm_events.rows(lat, lon)


_SAMPLERS = {"jrc_river_flood": jrc_flood_rows, "jrc_river_flood_europe": jrc_europe_rows, "storm_v4_wind": _storm_rows}


def sample(session: Session, layer_key: str, points: Optional[Iterable[tuple[float, float]]] = None,
           batch: int = 200) -> dict:
    """Sample a layer at every location not yet held for its version (all asset locations by default). Commits per
    batch. Returns {held, sampled, outside, failed}."""
    L = registry.layer(layer_key)
    from services.loss.projection import SOURCES, present_variant
    if layer_key in SOURCES.values():              # a source with maps per pathway: its present-day map when it serves
        serves_today = L["present"]["scenario"] == "present" and not L["present"].get("layer")
        today = [present_variant(L)] if serves_today else None                  # today's figure only, else every map
        return sample_maps(session, layer_key, today, points) if today else sample_projection(session, layer_key, points)
    if layer_key not in _SAMPLERS:
        raise registry.RegistryError(f"layer '{layer_key}' has no sampler yet")
    held = _held(session, layer_key, L["version"])
    if points is None:
        points = (asset_points_in(session, registry.coverage_countries(layer_key)) if L.get("coverage_countries")
                  else asset_points(session))
    todo = [p for p in points if p not in held]
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
                                                  value, cell_fraction, cell_mean, scenario, period, climate_model, caution)
            VALUES (:layer_key, :layer_version, :latitude, :longitude, :h3_cell, :rp_years, :status, :value,
                    :cell_fraction, :cell_mean, :scenario, :period, :climate_model, :caution)
            ON CONFLICT (layer_key, layer_version, latitude, longitude, rp_years, scenario, period, climate_model)
            DO NOTHING"""), [{**PRESENT, "caution": None, **r} for r in rows])


def prepare_book(session: Session, assets: list[dict], perils: Iterable[str], projected: bool = False) -> dict:
    """Sample, for one book's assets, every layer its run will read and has not sampled yet — so a newly added asset
    gets its figure from the run itself, not after a separate sampling job. Today's climate: each peril's global layer;
    the layer replacing it where in use, at the assets in its coverage countries; and, for flood, the protection map. A
    projected run: each peril's projection source, every map, and the layer holding its present day. Commits as it
    samples (the samples are reference data, append-only)."""
    from services.loss import engine, projection, protection
    pts = sorted({(float(a["latitude"]), float(a["longitude"])) for a in assets
                  if a.get("latitude") is not None and a.get("longitude") is not None})
    out = {}
    if projected:
        for peril in perils:
            key = projection.SOURCES.get(peril)
            if key:
                out[key] = sample_projection(session, key, pts)
                if projection.present_layer(key) != key:
                    out[projection.present_layer(key)] = sample(session, projection.present_layer(key), pts)
        return out
    for peril in perils:
        out[engine.LAYERS[peril]] = sample(session, engine.LAYERS[peril], pts)
        for k, L in registry.layers().items():
            if L.get("replaces") == engine.LAYERS[peril] and L.get("status") == "in_use":
                cover = registry.coverage_countries(k)
                out[k] = sample(session, k, sorted({(float(a["latitude"]), float(a["longitude"])) for a in assets
                                                    if a.get("latitude") is not None and a.get("longitude") is not None
                                                    and (a.get("country") or "").strip().upper() in cover}))
        if peril in protection.LAYERS:                 # river flood: the JRC map; coastal flood: COASTPROS-EU
            out[protection.LAYERS[peril]] = protection.sample(session, pts, key=protection.LAYERS[peril])
    return out


def sample_job(layer_key: str = "jrc_river_flood") -> dict:
    """The background job (services.tasks.jobs 'loss.sample_intensity'): its own session."""
    from core.db.session import get_session
    with get_session() as session:
        return sample(session, layer_key)
