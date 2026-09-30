"""Place points in WRI Aqueduct 4.0 basins and read ESRS's water-stress definitions off them
(data/reference/esrs/water_stress.json quotes each definition and names the Aqueduct field and categories it reads).

A point is placed by an exact point-in-polygon test on the basins of the current load whose bounding box holds it
(aqueduct_basins; no PostGIS at runtime). Categories are WRI's own coding: baseline water stress 3 = High (40-80 %),
4 = Extremely High (>80 %); baseline water depletion 3 = High (50-75 %), 4 = Extremely High (>75 %); -1 'Arid and Low
Water Use' is its own class (not a withdrawal ratio) and -9999 no data — neither is read as water stress.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from shapely import wkb
from shapely.geometry import Point
from sqlalchemy import text
from sqlalchemy.orm import Session

_REF = Path(__file__).resolve().parents[2] / "data" / "reference" / "esrs" / "water_stress.json"


@lru_cache(maxsize=1)
def definitions() -> dict:
    return json.loads(_REF.read_text())


def current_load(session: Session) -> dict | None:
    r = session.execute(text("""SELECT load_id::text AS load_id, version, data_vintage, sha256, n_basins, loaded_at
                                FROM aqueduct_loads WHERE retired_at IS NULL""")).mappings().first()
    return None if r is None else {**dict(r), "data_vintage": r["data_vintage"] and r["data_vintage"].isoformat(),
                                   "loaded_at": r["loaded_at"].isoformat()}


def basin_at(session: Session, lat: float, lon: float, load_id: str) -> dict | None:
    rows = session.execute(text("""
        SELECT string_id, name_0, name_1, bws_raw, bws_cat, bws_label, bwd_raw, bwd_cat, bwd_label, geom_wkb
        FROM aqueduct_basins
        WHERE load_id = CAST(:l AS uuid) AND minx <= :x AND maxx >= :x AND miny <= :y AND maxy >= :y
    """), {"l": load_id, "x": lon, "y": lat}).mappings().all()
    p = Point(lon, lat)
    hit = next((r for r in rows if wkb.loads(bytes(r["geom_wkb"])).covers(p)), None)
    return None if hit is None else {k: hit[k] for k in hit.keys() if k != "geom_wkb"}


def classify(session: Session, lat: float | None, lon: float | None, esrs_version: str) -> dict:
    """The point's Aqueduct basin and, criterion by criterion, whether the governing version's definition is met."""
    d = definitions()
    edition = d["versions"][esrs_version]
    load = current_load(session)
    if load is None:
        return {"status": "no_data", "reason": "WRI Aqueduct is not loaded"}
    if lat is None or lon is None:
        return {"status": "no_data", "reason": "the site has no coordinates"}
    b = basin_at(session, lat, lon, load["load_id"])
    if b is None:
        return {"status": "no_data", "reason": "the point lies in no Aqueduct basin", "load": load["load_id"]}
    out = []
    for c in d[edition]["criteria"]:
        if c.get("field") is None:
            out.append({"id": c["id"], "met": None, "not_assessed": c["not_assessed"]})
            continue
        cat = b[c["field"]]
        if cat in (d["arid_low_water_use"]["category"], d["no_data"]["category"]):
            out.append({"id": c["id"], "met": None, "category": cat, "label": b[c["field"].replace("_cat", "_label")]})
            continue
        out.append({"id": c["id"], "met": cat in c["categories"], "category": cat,
                    "label": b[c["field"].replace("_cat", "_label")]})
    assessed = [x["met"] for x in out if x["met"] is not None]
    met = True if any(assessed) else (False if assessed and len(assessed) == len(out) else None)
    return {"status": "classified", "edition": edition, "term": d[edition]["term"], "basin": b, "criteria": out,
            "in_area": met, "load": load["load_id"],
            "note": None if met is not None else "not every criterion of the definition could be assessed"}
