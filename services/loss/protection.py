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
isolated sampler (services.geo.raster_sampler, E170)."""
from __future__ import annotations

import logging
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.loss import registry

log = logging.getLogger(__name__)

LAYER = "jrc_flood_protection_europe"


def layer() -> dict:
    try:
        return registry.protection_layers()[LAYER]
    except KeyError:
        raise registry.RegistryError(f"protection layer '{LAYER}' is not registered")


def _path() -> str:
    return str(registry.ROOT / layer()["file"])


def rows(points: list[tuple[float, float]]) -> Optional[list[dict]]:
    """One row per (lat, lon): 'sampled' with the design return period of the pixel holding it, 'no_value' where the
    map holds none (−1), 'outside_coverage' off the map. None when the file is missing or a read failed."""
    from pyproj import Transformer

    from services.geo import raster_sampler
    P = layer()
    info = raster_sampler.info(_path())
    if info is None:
        return None
    to_map = Transformer.from_crs("EPSG:4326", info["crs"], always_xy=True)
    xy = [to_map.transform(lon, lat) for lat, lon in points]
    left, bottom, right, top = info["bounds"]
    inside = [left <= x < right and bottom < y <= top for x, y in xy]
    got = raster_sampler.sample(_path(), [p for p, i in zip(xy, inside) if i]) if any(inside) else []
    if got is None:
        return None
    vals = iter(got)
    out = []
    for (lat, lon), i in zip(points, inside):
        base = {"layer_key": LAYER, "layer_version": P["version"], "latitude": lat, "longitude": lon}
        if not i:
            out.append({**base, "status": "outside_coverage", "design_rp_years": None})
            continue
        v = next(vals)[0]
        ok = v == v and v != info["nodata"] and v >= 1
        out.append({**base, "status": "sampled" if ok else "no_value", "design_rp_years": float(v) if ok else None})
    return out


def sample(session: Session, points: Optional[Iterable[tuple[float, float]]] = None, chunk: int = 2000) -> dict:
    """Sample the protection map at every asset location it does not hold yet; commits per chunk."""
    from services.loss.intensity import asset_points
    P = layer()
    held = {(float(a), float(b)) for a, b in session.execute(text("""
        SELECT latitude, longitude FROM flood_protection_samples WHERE layer_key = :k AND layer_version = :v"""),
        {"k": LAYER, "v": P["version"]}).all()}
    todo = [p for p in (points if points is not None else asset_points(session)) if p not in held]
    counts = {"held": len(held), "sampled": 0, "no_value": 0, "outside_coverage": 0, "failed": 0}
    for i in range(0, len(todo), chunk):
        got = rows(todo[i:i + chunk])
        if got is None:
            counts["failed"] += len(todo[i:i + chunk])
            continue
        session.execute(text("""
            INSERT INTO flood_protection_samples (layer_key, layer_version, latitude, longitude, status, design_rp_years)
            VALUES (:layer_key, :layer_version, :latitude, :longitude, :status, :design_rp_years)
            ON CONFLICT (layer_key, layer_version, latitude, longitude) DO NOTHING"""), got)
        session.commit()
        for r in got:
            counts[r["status"]] += 1
    log.info("flood protection: %s", counts)
    return counts


def at(session: Session, lat: float, lon: float) -> tuple[Optional[float], str]:
    """(design return period in years, or None; the basis shown with the figure)."""
    P = layer()
    r = session.execute(text("""
        SELECT status, design_rp_years FROM flood_protection_samples
        WHERE layer_key = :k AND layer_version = :v AND latitude = :la AND longitude = :lo"""),
        {"k": LAYER, "v": P["version"], "la": lat, "lo": lon}).mappings().first()
    if r is None:
        return None, "protection unknown: the protection map has not been sampled at this location yet"
    if r["status"] == "sampled":
        return float(r["design_rp_years"]), (f"{LAYER} {P['version']}: defences designed for the "
                                             f"1-in-{r['design_rp_years']:g}-year river flood")
    if r["status"] == "no_value":
        return None, "protection unknown: the protection map holds no value at this location"
    return None, ("protection unknown: outside the protection map (geographical Europe bar Russia, Belarus, Ukraine "
                  "and the Caucasus)")


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
