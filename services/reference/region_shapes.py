"""The borders of the regions a regional calibration is fitted on and applied to (data/reference/regions/provenance.json
'shapes') — one region code per place, from two published sources only:

  nuts2      EU, EFTA and candidate countries: Eurostat/GISCO NUTS 2021 level 2, the union of its level-3 regions
             (data/reference/geo/nuts3_eu_20m_2021.geojson) — the codes Eurostat publishes regional crop yields under
  iso3166_2  the countries listed there: Natural Earth admin-1 (1:10m, public domain) — the polygon of each ISO 3166-2
             code, kept only when the code is in the national authority's own list (services.reference.regions)

A place belongs to the region whose polygon contains it; a place in no polygon has no region, never a nearest one.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from services.reference import regions

ROOT = Path(__file__).resolve().parents[2]
_ALIASES = {"EL": "GR", "UK": "GB"}           # Eurostat's country prefixes read as ISO 3166-1


class ShapesError(ValueError):
    pass


@lru_cache(maxsize=1)
def reference() -> dict:
    return regions.provenance()["shapes"]


def country_of(code: str) -> str:
    """ISO 3166-1 alpha-2 country of a region code: 'US-KS' → 'US', 'ES42' → 'ES', 'EL30' → 'GR'."""
    cc = code.split("-", 1)[0] if "-" in code[:3] else code[:2]
    return _ALIASES.get(cc, cc)


def scheme_of(country: str) -> str | None:
    """'nuts2' or 'iso3166_2' — the scheme a country's regions are drawn in (None: no regions held)."""
    if country in reference()["iso3166_2"]["countries"]:
        return "iso3166_2"
    if country in nuts2_countries():
        return "nuts2"
    return None


@lru_cache(maxsize=1)
def nuts2_countries() -> frozenset[str]:
    doc = json.loads((ROOT / reference()["nuts2"]["file"]).read_text(encoding="utf-8"))
    return frozenset(_ALIASES.get(f["properties"]["CNTR_CODE"], f["properties"]["CNTR_CODE"]) for f in doc["features"])


def _nuts2() -> dict:
    from shapely.geometry import shape
    from shapely.ops import unary_union
    doc = json.loads((ROOT / reference()["nuts2"]["file"]).read_text(encoding="utf-8"))
    parts: dict[str, list] = {}
    for f in doc["features"]:
        if f["properties"]["LEVL_CODE"] != 3:
            raise ShapesError(f"{f['properties']['NUTS_ID']}: the NUTS file holds a level other than 3")
        parts.setdefault(f["properties"]["NUTS_ID"][:4], []).append(shape(f["geometry"]))
    return {code: unary_union(p) for code, p in parts.items()}


def _iso3166_2() -> dict:
    """Read with pyshp (pure Python) — no GDAL in the API's process (E170)."""
    import io
    import zipfile

    import shapefile
    from shapely.geometry import shape
    from shapely.ops import unary_union
    ref = reference()["iso3166_2"]
    stem = ref["member"].rsplit(".", 1)[0]
    with zipfile.ZipFile(ROOT / ref["file"]) as z:
        part = {ext: io.BytesIO(z.read(f"{stem}.{ext}")) for ext in ("shp", "shx", "dbf")}
    r = shapefile.Reader(**part, encoding="utf-8")
    names = [f[0].lower() for f in r.fields[1:]]
    i_code, i_cc = names.index("iso_3166_2"), names.index("iso_a2")
    official = {cc: regions.of_country(cc) for cc in ref["countries"]}
    for cc, codes in official.items():
        if not codes:
            raise ShapesError(f"{cc}: no official subdivision list is held — a border is kept only for a listed code")
    out: dict[str, list] = {}
    for sr in r.iterShapeRecords():
        code, cc = sr.record[i_code], sr.record[i_cc]
        if cc in official and code in official[cc]:      # Natural Earth's placeholders ('AU-X02~') are not codes
            out.setdefault(code, []).append(shape(sr.shape.__geo_interface__))
    return {code: unary_union(p) for code, p in out.items()}


@lru_cache(maxsize=1)
def shapes() -> dict:
    """{region code: shapely geometry (lon/lat)} — every region of both schemes."""
    return {**_nuts2(), **_iso3166_2()}


def fingerprint() -> str:
    """What the borders are read from — the files' recorded bytes and the scheme settings."""
    h = hashlib.sha256(json.dumps(reference(), sort_keys=True).encode())
    for k in ("nuts2", "iso3166_2"):
        h.update((ROOT / reference()[k]["file"]).read_bytes()[:1 << 20])
    return h.hexdigest()[:16]


@lru_cache(maxsize=1)
def _index():
    from shapely.strtree import STRtree
    codes = sorted(shapes())
    geoms = [shapes()[c] for c in codes]
    return STRtree(geoms), codes, geoms


def region_of(lat: float, lon: float) -> str | None:
    """The region whose polygon contains the point (None when none does)."""
    from shapely.geometry import Point
    tree, codes, geoms = _index()
    p = Point(lon, lat)
    hits = [codes[i] for i in tree.query(p) if geoms[i].contains(p)]
    if len(hits) > 1:
        raise ShapesError(f"({lat}, {lon}) lies in {len(hits)} regions ({', '.join(hits)}) — the borders overlap")
    return hits[0] if hits else None
