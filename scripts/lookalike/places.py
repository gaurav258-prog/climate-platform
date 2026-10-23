"""Real places for the lookalike books: each asset sits in a real 100 m cell where the EU's Global Human Settlement Layer
maps buildings — never a made-up coordinate.

Source: JRC GHSL R2023A, epoch 2020, 100 m Mollweide (ESRI:54009) — GHS-BUILT-S (built-up surface, m² per cell) and
GHS-POP (residents per cell), CC BY 4.0, on disk in data/exposure_val/ghsl (data/exposure_val/MANIFEST.md). Regions:
Eurostat GISCO NUTS-2021 level 3 (services/geo/regions.NUTS3_PATH).

  draw(regions, n, weight=…, seed=…)   n distinct built-up cells inside the given NUTS-3 regions (a code or a prefix:
                                       'DE', 'ES61', 'ES616'), shared out over the regions by their total weight and
                                       drawn within each in proportion to it: 'residents' for homes, 'built' for
                                       offices, shops, warehouses and plants. The same seed always draws the same cells.

A cell qualifies when its built-up surface is at least MIN_BUILT_M2 of its 10,000 m². Each place keeps its region, the
built-up surface and residents of its cell, so where it came from can be checked.
"""
from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from services.geo.regions import NUTS3_PATH

ROOT = Path(__file__).resolve().parents[2]
GHSL = ROOT / "data" / "exposure_val" / "ghsl"
CACHE = ROOT / "data" / "exposure_val" / "ghsl_tif"        # the tiles unzipped once (gitignored with data/exposure_val)
MIN_BUILT_M2 = 1500.0
MOLLWEIDE = "ESRI:54009"


@dataclass(frozen=True)
class Place:
    lat: float
    lon: float
    nuts3: str
    region: str
    country: str
    built_m2: float
    residents: float


@lru_cache(maxsize=1)
def _regions() -> dict:
    return {f["properties"]["NUTS_ID"]: f for f in json.loads(NUTS3_PATH.read_text())["features"]}


def regions_of(codes: list[str]) -> list[str]:
    """Every NUTS-3 region a code or prefix names, in code order."""
    out = sorted({k for k in _regions() for c in codes if k.startswith(c)})
    if not out:
        raise ValueError(f"no NUTS-3 region matches {codes}")
    return out


def _tif(kind: str, r: int, c: int) -> Path | None:
    """The unzipped tile, extracted on first use; None where the tile does not exist (open sea)."""
    z = GHSL / f"{kind}_R{r}_C{c}.zip"
    if not z.exists():
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(z) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".tif"))
        out = CACHE / name
        if not out.exists():
            zf.extract(name, CACHE)
    return out


@lru_cache(maxsize=1)
def _tile_bounds() -> dict:
    """(row, col) → the tile's Mollweide bounds, read from each tile's own header."""
    import rasterio
    out = {}
    for z in sorted(GHSL.glob("BUILT_S_R*_C*.zip")):
        r, c = (int(x[1:]) for x in z.stem.split("_")[-2:])
        p = _tif("BUILT_S", r, c)
        with rasterio.open(p) as ds:
            out[(r, c)] = tuple(ds.bounds)
    return out


def _cells(nuts3: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """x, y (Mollweide cell centres), built-up m² and residents of every qualifying cell inside one region."""
    import rasterio
    from pyproj import Transformer
    from rasterio.features import geometry_mask
    from rasterio.windows import from_bounds
    from shapely.geometry import box, mapping, shape
    from shapely.ops import transform
    to_moll = Transformer.from_crs("EPSG:4326", MOLLWEIDE, always_xy=True).transform
    geom = transform(to_moll, shape(_regions()[nuts3]["geometry"]))
    xs, ys, built, pop = [], [], [], []
    for (r, c), b in _tile_bounds().items():
        part = geom.intersection(box(*b))
        if part.is_empty:
            continue
        bp, pp = _tif("BUILT_S", r, c), _tif("POP", r, c)
        with rasterio.open(bp) as ds:
            win = from_bounds(*part.bounds, transform=ds.transform).round_offsets().round_lengths()
            bv = ds.read(1, window=win, boundless=True, fill_value=0).astype("float64")
            wt = ds.window_transform(win)
        pv = np.zeros_like(bv)
        if pp:
            with rasterio.open(pp) as ds:
                pv = ds.read(1, window=win, boundless=True, fill_value=0).astype("float64")
                pv[pv < 0] = 0
        inside = ~geometry_mask([mapping(part)], out_shape=bv.shape, transform=wt)
        rows, cols = np.nonzero(inside & (bv >= MIN_BUILT_M2))
        cx, cy = rasterio.transform.xy(wt, rows, cols)
        xs.append(np.asarray(cx)); ys.append(np.asarray(cy))
        built.append(bv[rows, cols]); pop.append(pv[rows, cols])
    if not xs:
        return (np.array([]),) * 4
    return np.concatenate(xs), np.concatenate(ys), np.concatenate(built), np.concatenate(pop)


def draw(regions: list[str], n: int, *, weight: str = "residents", seed: int = 2026) -> list[Place]:
    if weight not in ("residents", "built"):
        raise ValueError("weight is 'residents' or 'built'")
    from pyproj import Transformer
    to_geo = Transformer.from_crs(MOLLWEIDE, "EPSG:4326", always_xy=True).transform
    rng = np.random.default_rng(seed)
    per = {k: _cells(k) for k in regions_of(regions)}
    w = {k: float((v[3] if weight == "residents" else v[2]).sum()) for k, v in per.items()}
    total = sum(w.values())
    if total <= 0:
        raise ValueError(f"no built-up cell in {regions}")
    keys = sorted(per)
    share = rng.multinomial(n, [w[k] / total for k in keys])          # regions by their weight, then cells within each
    out = []
    for k, m in zip(keys, share):
        x, y, b, p = per[k]
        if m == 0 or not len(x):
            continue
        wk = p if weight == "residents" else b
        prob = wk / wk.sum() if wk.sum() > 0 else None
        idx = rng.choice(len(x), size=min(m, len(x)), replace=False, p=prob)
        props = _regions()[k]["properties"]
        for i in idx:
            lon, lat = to_geo(float(x[i]), float(y[i]))
            out.append(Place(round(lat, 6), round(lon, 6), k, props["NUTS_NAME"], props["CNTR_CODE"],
                             float(b[i]), round(float(p[i]), 1)))
    return out


def built_m2_at(lat: float, lon: float) -> float:
    """The built-up surface (m²) of the 100 m GHSL cell holding this point; 0 at sea or outside the tiles."""
    import rasterio
    from pyproj import Transformer
    x, y = Transformer.from_crs("EPSG:4326", MOLLWEIDE, always_xy=True).transform(lon, lat)
    for (r, c), b in _tile_bounds().items():
        if b[0] <= x < b[2] and b[1] < y <= b[3]:
            with rasterio.open(_tif("BUILT_S", r, c)) as ds:
                return float(next(ds.sample([(x, y)]))[0])
    return 0.0
