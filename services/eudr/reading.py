"""A plot's satellite reading for EUDR (E94; the user's decision): what the dataset shows inside the plot after the cut-off
date — never a verdict. Deforestation is 'the conversion of forest to agricultural use' (Art. 2(3)) and a forest is
'more than 0,5 hectares with trees higher than 5 metres and a canopy cover of more than 10 %' (Art. 2(4)); tree-cover loss
in a dataset shows neither the land use nor the tree height. A reading is therefore a risk the operator weighs in its
Art. 10 assessment, recorded with exactly what was read.

  cut-off            31 December 2020 (Art. 2(13)) — loss in 2021 or later counts
  always recorded    tree-cover loss after the cut-off, unmasked
  only when stated   loss on pixels with at least the stated tree cover in 2000 (the person running the reading states
                     the percentage; the platform supplies none)
  a point plot       has no area: the person states the radius to read around it, or the reading is 'not assessable'
  across data tiles  'not assessable' (the reading covers one tile), named — never half a reading
Every reading is kept (eudr_plot_assessment, append-only) with the geometry it read: a plot moved or redrawn afterwards
has no current reading until it is read again. Heavy raster reads run as a job (services.tasks.jobs), never in the API.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

CUTOFF = date(2020, 12, 31)                       # Art. 2(13)
DATASET = "hansen_gfc"


class ReadingError(ValueError):
    pass


def geometry_of(plot: dict) -> dict:
    """The plot as read: its boundary, else its point (GeoJSON)."""
    g = plot.get("plot_geometry")
    if g:
        return json.loads(g) if isinstance(g, str) else g
    if plot.get("latitude") is None or plot.get("longitude") is None:
        raise ReadingError("the plot has no location")
    return {"type": "Point", "coordinates": [plot["longitude"], plot["latitude"]]}


def geometry_sha(geom: dict) -> str:
    return hashlib.sha256(json.dumps(geom, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _tiles(footprint) -> set[str]:
    from services.intelligence.forest import tile_id
    minx, miny, maxx, maxy = footprint.bounds
    return {tile_id(lat, lon) for lat in (miny, maxy) for lon in (minx, maxx)}


def read(geom: dict, *, treecover_min_pct: Optional[int], point_radius_m: Optional[float]) -> dict:
    """The reading of one geometry: {outcome, loss_ha, first_loss_year, reason, method} (no database)."""
    from shapely.geometry import shape

    from services.intelligence import forest as F
    g = shape(geom)
    method = {"dataset": DATASET, "dataset_version": F.GFC_VERSION, "cutoff": CUTOFF.isoformat(),
              "treecover_min_pct": treecover_min_pct, "point_radius_m": point_radius_m, "geometry_type": g.geom_type}
    if g.geom_type == "Point":
        if not point_radius_m:
            return {"outcome": "not_assessable", "loss_ha": None, "first_loss_year": None, "method": method,
                    "reason": "a point has no area — state the radius to read around it, or provide the plot's boundary"}
        c = g.centroid
        footprint = g.buffer(point_radius_m / (111_320.0 * max(math.cos(math.radians(c.y)), 1e-6)))
    else:
        footprint = g
    tiles = _tiles(footprint)
    if len(tiles) > 1:
        return {"outcome": "not_assessable", "loss_ha": None, "first_loss_year": None, "method": {**method, "tiles": sorted(tiles)},
                "reason": f"the plot crosses data tiles {', '.join(sorted(tiles))} — a reading covers one tile"}
    raw = F.forest_loss_since(footprint, cutoff_year=CUTOFF.year, min_treecover_pct=0, point_buffer_m=0.0)
    if raw.insufficient:
        return {"outcome": "not_assessable", "loss_ha": None, "first_loss_year": None, "method": {**method, "tile": raw.tile},
                "reason": f"the dataset could not be read here ({raw.source})"}
    method.update(tile=raw.tile, source=raw.source, pixels=raw.total_pixels, loss_pixels_unmasked=raw.loss_pixels,
                  loss_ha_unmasked=raw.loss_ha, first_loss_year_unmasked=raw.first_loss_year)
    loss_ha, first, pixels = raw.loss_ha, raw.first_loss_year, raw.loss_pixels
    if treecover_min_pct:
        masked = F.forest_loss_since(footprint, cutoff_year=CUTOFF.year, min_treecover_pct=treecover_min_pct, point_buffer_m=0.0)
        if masked.insufficient:
            return {"outcome": "not_assessable", "loss_ha": None, "first_loss_year": None, "method": method,
                    "reason": f"the 2000 tree-cover layer could not be read here ({masked.source})"}
        method.update(loss_pixels_masked=masked.loss_pixels, forest_pixels_2000=masked.forest_pixels)
        loss_ha, first, pixels = masked.loss_ha, masked.first_loss_year, masked.loss_pixels
    return {"outcome": "loss_after_cutoff" if pixels else "no_loss_detected", "loss_ha": loss_ha, "first_loss_year": first,
            "reason": None, "method": method}


def record(session: Session, org_id: str, plot_id: str, user_id: Optional[str], *, treecover_min_pct: Optional[int] = None,
           point_radius_m: Optional[float] = None) -> dict:
    """Read one plot and keep the reading."""
    p = session.execute(text("""SELECT plot_id::text AS plot_id, latitude, longitude, plot_geometry FROM sc_sourcing_plots
                                WHERE plot_id = CAST(:p AS uuid) AND org_id = CAST(:o AS uuid)"""),
                        {"p": plot_id, "o": org_id}).mappings().first()
    if p is None:
        raise ReadingError("no such plot in this organisation")
    geom = geometry_of(dict(p))
    r = read(geom, treecover_min_pct=treecover_min_pct, point_radius_m=point_radius_m)
    session.execute(text("""
        INSERT INTO eudr_plot_assessment (plot_id, dataset, dataset_version, geometry_sha256, cutoff, outcome, loss_ha,
                                          first_loss_year, reason, method, assessed_by)
        VALUES (CAST(:p AS uuid), :d, :v, :g, :c, :o, :l, :f, :r, CAST(:m AS jsonb), CAST(:u AS uuid))"""),
        {"p": plot_id, "d": DATASET, "v": r["method"]["dataset_version"], "g": geometry_sha(geom), "c": CUTOFF,
         "o": r["outcome"], "l": r["loss_ha"], "f": r["first_loss_year"], "r": r["reason"], "m": json.dumps(r["method"]),
         "u": user_id})
    return {"plot_id": plot_id, **r}


def current(session: Session, plot_ids: list[str]) -> dict[str, Optional[dict]]:
    """Each plot's latest reading OF ITS CURRENT GEOMETRY (None: never read, or read before it moved)."""
    rows = session.execute(text("""
        SELECT DISTINCT ON (a.plot_id) a.plot_id::text AS plot_id, a.outcome, CAST(a.loss_ha AS FLOAT) AS loss_ha,
               a.first_loss_year, a.reason, a.method, a.geometry_sha256, a.assessed_at,
               p.latitude, p.longitude, p.plot_geometry
        FROM eudr_plot_assessment a JOIN sc_sourcing_plots p USING (plot_id)
        WHERE a.plot_id = ANY(CAST(:ids AS uuid[])) ORDER BY a.plot_id, a.seq DESC"""), {"ids": plot_ids}).mappings().all()
    out: dict[str, Optional[dict]] = {pid: None for pid in plot_ids}
    for r in rows:
        try:
            same = geometry_sha(geometry_of(dict(r))) == r["geometry_sha256"]
        except ReadingError:
            same = False
        out[r["plot_id"]] = ({k: r[k] for k in ("outcome", "loss_ha", "first_loss_year", "reason", "method")}
                             | {"assessed_at": r["assessed_at"].isoformat()}) if same else None
    return out


def run_job(org_id: str, plot_ids: list[str], user_id: Optional[str], treecover_min_pct: Optional[int] = None,
            point_radius_m: Optional[float] = None) -> dict:
    """The job (services.tasks.jobs 'eudr.read_plots'): each plot read and kept in its own transaction."""
    from core.db.session import get_session
    done = 0
    for pid in plot_ids:
        with get_session() as s:
            record(s, org_id, pid, user_id, treecover_min_pct=treecover_min_pct, point_radius_m=point_radius_m)
            s.commit()
            done += 1
    return {"read": done}
