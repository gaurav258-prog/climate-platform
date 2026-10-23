"""Flood defences (product owner's decisions, 2026-10-16; data/reference/loss_protocol.json 'flood_protection').

A published protection standard — the design return period, in years, of the local defences against river floods
(the JRC European map, jrc_flood_protection_europe) — is sampled once per location into flood_protection_samples, and
applied to a flood loss as its publisher's method states it (Ward et al. 2020, section 6, p. 5): the protection is a
vertical line on the loss–exceedance curve at p = 1 / design years; damage from floods more frequent than the line is
set to 0; the defended expected annual loss is the area to the left of the line.

On the run's own curve (straight lines in annual exceedance probability between the return periods held, the rarest
loss held beyond the rarest): a line more frequent than the most frequent period held removes nothing, and a line rarer
than the rarest leaves only the held tail beyond it. A location the map does not cover, or where it holds no value, has
no defended figure: its undefended figure is shown, labelled 'protection unknown'. Every raster read goes through the
isolated sampler (services.geo.raster_sampler, E170).

Coastal flood (the product owner's decisions of 2026-10-23) reads COASTPROS-EU (coastpros_eu): one entry per coastal NUTS2
region, stated as text and read by the decided rule (level_of): a single number is the level; a plain range is a range of
levels, sampled as its lower and upper level — the defended loss then a range, with no central figure (at_range); a list,
a condition or a note is no level ('not_a_level'), an empty entry no value, a place in no listed region off the map —
each 'protection unknown'. The regions are polygons read from the dataset's shapefile.

  LAYERS                         each peril's protection layer: river flood → the JRC map, coastal flood → COASTPROS-EU
  level_of(entry)                (lower, upper or None) of a COASTPROS-EU entry, or None when it is not a level
  at(session, lat, lon)          (level or None, message code) — river flood
  at_range(session, lat, lon, k) (lower, upper or None, message code) — any protection layer"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.loss import registry

log = logging.getLogger(__name__)

LAYER = "jrc_flood_protection_europe"
LAYERS = {"flood": LAYER, "coastal_flood": "coastpros_eu"}
_NUM = r"\d+(?:[.,]\d+)?"


def layer(key: str = LAYER) -> dict:
    try:
        return registry.protection_layers()[key]
    except KeyError:
        raise registry.RegistryError(f"protection layer '{key}' is not registered")


def _path(key: str = LAYER) -> str:
    return str(registry.ROOT / layer(key)["file"])


def level_of(entry) -> Optional[tuple[float, Optional[float]]]:
    """A COASTPROS-EU entry read by the decided rule (2026-10-23): a single number → (n, None); a plain range 'a-b' →
    (lower, upper); anything else → None (not a level)."""
    import re
    if entry is None or entry != entry:
        return None
    s = str(entry).strip()
    if re.fullmatch(_NUM, s):
        return float(s.replace(",", ".")), None
    m = re.fullmatch(rf"({_NUM})\s*-\s*({_NUM})", s)
    if m:
        a, b = sorted(float(x.replace(",", ".")) for x in m.groups())
        return (a, b) if a != b else (a, None)
    return None


@lru_cache(maxsize=2)
def _regions(key: str, _version: int):
    """(STRtree, [(polygon, entry)]) of a region layer's shapefile, read once per version of the file."""
    import geopandas as gpd
    from shapely import STRtree
    P = layer(key)
    g = gpd.read_file(registry.ROOT / P["file"]).to_crs("EPSG:4326")
    items = [(geom, row[P["reads"]]) for geom, (_i, row) in zip(g.geometry, g.iterrows()) if geom is not None]
    return STRtree([p for p, _e in items]), items


def _region_rows(points: list[tuple[float, float]], key: str) -> list[dict]:
    """One row per (lat, lon) of a region layer: the region holding the location, its entry read by level_of."""
    from shapely.geometry import Point
    P = layer(key)
    tree, items = _regions(key, (registry.ROOT / P["file"]).stat().st_mtime_ns)
    out = []
    for lat, lon in points:
        base = {"layer_key": key, "layer_version": P["version"], "latitude": lat, "longitude": lon,
                "design_rp_years": None, "design_rp_high_years": None}
        pt = Point(lon, lat)
        hit = next((items[i] for i in tree.query(pt) if items[i][0].covers(pt)), None)
        if hit is None:
            out.append({**base, "status": "outside_coverage"})
            continue
        entry = hit[1]
        lv = level_of(entry)
        if lv is not None:
            out.append({**base, "status": "sampled", "design_rp_years": lv[0], "design_rp_high_years": lv[1]})
        else:
            empty = entry is None or entry != entry or not str(entry).strip()
            out.append({**base, "status": "no_value" if empty else "not_a_level"})
    return out


def rows(points: list[tuple[float, float]], key: str = LAYER) -> Optional[list[dict]]:
    """One row per (lat, lon): 'sampled' with the design return period of the pixel holding it, 'no_value' where the
    map holds none (−1), 'outside_coverage' off the map. None when the file is missing or a read failed."""
    if layer(key).get("kind") == "regions":
        return _region_rows(points, key)
    from pyproj import Transformer

    from services.geo import raster_sampler
    P = layer(key)
    info = raster_sampler.info(_path(key))
    if info is None:
        return None
    to_map = Transformer.from_crs("EPSG:4326", info["crs"], always_xy=True)
    xy = [to_map.transform(lon, lat) for lat, lon in points]
    left, bottom, right, top = info["bounds"]
    inside = [left <= x < right and bottom < y <= top for x, y in xy]
    got = raster_sampler.sample(_path(key), [p for p, i in zip(xy, inside) if i]) if any(inside) else []
    if got is None:
        return None
    vals = iter(got)
    out = []
    for (lat, lon), i in zip(points, inside):
        base = {"layer_key": key, "layer_version": P["version"], "latitude": lat, "longitude": lon,
                "design_rp_high_years": None}
        if not i:
            out.append({**base, "status": "outside_coverage", "design_rp_years": None})
            continue
        v = next(vals)[0]
        ok = v == v and v != info["nodata"] and v >= 1
        out.append({**base, "status": "sampled" if ok else "no_value", "design_rp_years": float(v) if ok else None})
    return out


def sample(session: Session, points: Optional[Iterable[tuple[float, float]]] = None, chunk: int = 2000,
           key: str = LAYER) -> dict:
    """Sample a protection layer at every asset location it does not hold yet; commits per chunk."""
    from services.loss.intensity import asset_points
    P = layer(key)
    held = {(float(a), float(b)) for a, b in session.execute(text("""
        SELECT latitude, longitude FROM flood_protection_samples WHERE layer_key = :k AND layer_version = :v"""),
        {"k": key, "v": P["version"]}).all()}
    todo = [p for p in (points if points is not None else asset_points(session)) if p not in held]
    counts = {"held": len(held), "sampled": 0, "no_value": 0, "outside_coverage": 0, "not_a_level": 0, "failed": 0}
    for i in range(0, len(todo), chunk):
        got = rows(todo[i:i + chunk], key)
        if got is None:
            counts["failed"] += len(todo[i:i + chunk])
            continue
        session.execute(text("""
            INSERT INTO flood_protection_samples (layer_key, layer_version, latitude, longitude, status, design_rp_years,
                                                  design_rp_high_years)
            VALUES (:layer_key, :layer_version, :latitude, :longitude, :status, :design_rp_years, :design_rp_high_years)
            ON CONFLICT (layer_key, layer_version, latitude, longitude) DO NOTHING"""), got)
        session.commit()
        for r in got:
            counts[r["status"]] += 1
    log.info("flood protection %s: %s", key, counts)
    return counts


def at(session: Session, lat: float, lon: float) -> tuple[Optional[float], str]:
    """(design return period in years, or None; the message code of the basis shown with the figure —
    data/reference/messages.en.json loss.protection.*)."""
    P = layer()
    r = session.execute(text("""
        SELECT status, design_rp_years FROM flood_protection_samples
        WHERE layer_key = :k AND layer_version = :v AND latitude = :la AND longitude = :lo"""),
        {"k": LAYER, "v": P["version"], "la": lat, "lo": lon}).mappings().first()
    if r is None:
        return None, "loss.protection.not_read"
    if r["status"] == "sampled":
        return float(r["design_rp_years"]), "loss.protection.level"
    if r["status"] == "no_value":
        return None, "loss.protection.no_value"
    return None, "loss.protection.off_map"


def at_range(session: Session, lat: float, lon: float, key: str) -> tuple[Optional[float], Optional[float], str]:
    """(lower level or None, upper level or None, message code) of a protection layer at a location: a single level
    has no upper; a range both; protection unknown neither — with why (data/reference/messages.en.json)."""
    P = layer(key)
    r = session.execute(text("""
        SELECT status, design_rp_years, design_rp_high_years FROM flood_protection_samples
        WHERE layer_key = :k AND layer_version = :v AND latitude = :la AND longitude = :lo"""),
        {"k": key, "v": P["version"], "la": lat, "lo": lon}).mappings().first()
    codes = P.get("codes") or {}
    if r is None:
        return None, None, "loss.protection.not_read"
    if r["status"] == "sampled":
        hi = r["design_rp_high_years"]
        return float(r["design_rp_years"]), (float(hi) if hi is not None else None), \
            ("loss.protection.range" if hi is not None else "loss.protection.level")
    return None, None, codes.get(r["status"], {"no_value": "loss.protection.no_value",
                                                 "not_a_level": "loss.protection.not_a_level"}.get(r["status"],
                                                                                                  "loss.protection.off_map"))


def _area(points: list[tuple[float, float]], lo: float, hi: float) -> float:
    """Area under the straight lines through `points` ((probability, loss), probability ascending) between lo and hi."""
    out = 0.0
    for (p0, l0), (p1, l1) in zip(points, points[1:]):
        a, b = max(p0, lo), min(p1, hi)
        if b <= a:
            continue
        la = l0 + (l1 - l0) * (a - p0) / (p1 - p0)
        lb = l0 + (l1 - l0) * (b - p0) / (p1 - p0)
        out += (b - a) * (la + lb) / 2
    return out


def defended_eal(losses: dict[int, float], design_rp: float) -> float:
    """The expected annual loss with the protection line at p = 1 / design_rp: the area under the run's loss–exceedance
    curve at probabilities at or below p — the curve as services.loss.engine.eal reads it (the rarest loss held from
    p = 0 to the rarest period's probability; straight lines between the periods held; nothing more frequent than the
    most frequent period held)."""
    rps = sorted(losses)
    pts = [(0.0, losses[rps[-1]])] + [(1.0 / rp, losses[rp]) for rp in reversed(rps)]
    return _area(pts, 0.0, min(1.0 / design_rp, 1.0 / rps[0]))


def sample_job() -> dict:
    """The background job (services.tasks.jobs 'loss.sample_protection'): its own session."""
    from core.db.session import get_session
    with get_session() as session:
        return sample(session)
