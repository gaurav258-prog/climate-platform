"""Where each crop grows, per origin, on the ERA5-Land grid (E163): the weights an origin's weather is averaged by.

A crop names its map and layers in the registry (crop_map); data/reference/crop_maps.json names the files. Each map cell
with harvested area gives its area to the ERA5-Land 0.1° cell nearest its centre and to the country whose GISCO 2020
polygon contains its centre (Eurostat's EL and UK read as GR and GB). Computed once per map version and country file,
kept under data/datasets/derived (git-ignored), rebuilt when either changes.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import zipfile
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "data" / "reference" / "crop_maps.json"
DERIVED = ROOT / "data" / "datasets" / "derived" / "crop_area_weights"
WEIGHTS_VERSION = "crop-area-weights-v1"
ERA5_NX, ERA5_NY, ERA5_RES = 3600, 1801, 0.1
_ALIASES = {"EL": "GR", "UK": "GB"}


@lru_cache(maxsize=1)
def reference() -> dict:
    return json.loads(REF.read_text(encoding="utf-8"))


def crop_map(commodity: str) -> dict | None:
    from ml.features.crop_registry import crop
    return crop(commodity).get("crop_map")


def _map_array(map_key: str, layer: str) -> tuple[np.ndarray, float]:
    """(harvested ha on a north-up global grid starting at 90°N, 180°W; cell size in degrees)."""
    m = reference()["maps"][map_key]
    member = m["member"].format(layer=layer)
    path = ROOT / m["file"]
    if m["format"] == "geotiff":
        import rasterio
        with rasterio.open(f"/vsizip/{path}/{member}") as r:
            a = r.read(1).astype(np.float64)
            res = r.transform.a
            if abs(r.transform.c + 180) > 1e-6 or abs(r.transform.f - 90) > 1e-6:
                raise ValueError(f"{member}: not a global grid starting at 90°N 180°W")
        a[~np.isfinite(a) | (a < 0)] = 0.0
        return a, res
    import xarray as xr
    cache = DERIVED / "extracted" / Path(member).name
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path) as z, z.open(member) as src:
            tmp = cache.with_suffix(".part")
            tmp.write_bytes(src.read())
            tmp.replace(cache)
    ds = xr.open_dataset(cache)
    a = ds[m["variable"]].values.astype(np.float64)
    lat = ds["lat"].values
    res = float(abs(lat[1] - lat[0]))
    if lat[0] < lat[-1]:
        a = a[::-1, :]                                      # north-up
    a[~np.isfinite(a) | (a < 0)] = 0.0
    return a, res


@lru_cache(maxsize=4)
def _countries(ny: int, nx: int, res: float) -> tuple[np.ndarray, tuple[str, ...]]:
    """(index grid — 0 none, k → codes[k-1] — of the country whose polygon contains each cell's centre; codes)."""
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    from shapely.geometry import shape
    doc = json.load(gzip.open(ROOT / reference()["countries"]["file"]))
    codes = tuple(sorted({_ALIASES.get(f["properties"]["CNTR_ID"], f["properties"]["CNTR_ID"]) for f in doc["features"]}))
    pos = {c: i + 1 for i, c in enumerate(codes)}
    shapes = ((shape(f["geometry"]), pos[_ALIASES.get(f["properties"]["CNTR_ID"], f["properties"]["CNTR_ID"])])
              for f in doc["features"])
    grid = rasterize(shapes, out_shape=(ny, nx), transform=from_origin(-180.0, 90.0, res, res), fill=0, dtype="int32")
    return grid, codes


def fingerprint(commodity: str) -> str:
    """What the weights are computed from: the map's recorded checksum (data/reference/supply_datasets.json), the layers,
    the country file and this module's version."""
    cm = crop_map(commodity)
    if not cm:
        return ""
    manifest = json.loads((ROOT / "data" / "reference" / "supply_datasets.json").read_text(encoding="utf-8"))
    key = {"mapspam2020": "mapspam_2020_harvested_area", "cropgrids108": "cropgrids_v1_08"}[cm["map"]]
    h = hashlib.sha256(WEIGHTS_VERSION.encode())
    h.update(json.dumps(manifest.get(key, {}).get("files", []), sort_keys=True).encode())
    h.update(json.dumps(cm, sort_keys=True).encode())
    h.update((ROOT / reference()["countries"]["file"]).read_bytes()[:1 << 20])
    return h.hexdigest()[:16]


def weights(commodity: str) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """{origin ISO2: (ERA5 flat cell index, harvested ha)} for a crop — computed once per fingerprint and kept."""
    cm = crop_map(commodity)
    if not cm:
        return {}
    fp = fingerprint(commodity)
    out_file = DERIVED / f"{commodity.replace(' ', '_')}_{fp}.npz"
    if out_file.exists():
        z = np.load(out_file, allow_pickle=False)
        return {k[:-4]: (z[k], z[k[:-4] + "_w"]) for k in z.files if k.endswith("_idx")}
    total = None
    for layer in cm["layers"]:
        a, res = _map_array(cm["map"], layer)
        total = a if total is None else total + a
    ny, nx = total.shape
    grid, codes = _countries(ny, nx, res)
    ii, jj = np.nonzero(total > 0)
    lat = 90.0 - (ii + 0.5) * res
    lon = -180.0 + (jj + 0.5) * res
    ei = np.clip(np.rint((90.0 - lat) / ERA5_RES).astype(np.int64), 0, ERA5_NY - 1)
    ej = np.rint(np.mod(lon, 360.0) / ERA5_RES).astype(np.int64) % ERA5_NX
    flat = ei * ERA5_NX + ej
    cidx = grid[ii, jj]
    area = total[ii, jj]
    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    keep = cidx > 0
    order = np.lexsort((flat[keep], cidx[keep]))
    c_s, f_s, a_s = cidx[keep][order], flat[keep][order], area[keep][order]
    for k in np.unique(c_s):
        sel = c_s == k
        f_k, a_k = f_s[sel], a_s[sel]
        u, inv = np.unique(f_k, return_inverse=True)
        out[codes[k - 1]] = (u.astype(np.int32), np.bincount(inv, weights=a_k))
    DERIVED.mkdir(parents=True, exist_ok=True)
    tmp = out_file.with_suffix(".part.npz")
    np.savez_compressed(tmp, **{f"{c}_idx": v[0] for c, v in out.items()}, **{f"{c}_w": v[1] for c, v in out.items()})
    tmp.replace(out_file)
    return out
