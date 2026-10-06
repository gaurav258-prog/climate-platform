"""The STORM v4 synthetic tropical-cyclone event set (E171): 10,000 simulated years per basin (Bloemendaal et al.,
data/reference/event_sets.json) held as compact arrays, and the wind each location should expect at a return period.

  compact()        the 60 published text files → one array file per basin under data/datasets/storm_v4 (track points
                   sorted by latitude: synthetic year, cyclone number, position, maximum wind m/s, radius to maximum
                   wind km), each file's checksum recorded in data/reference/supply_datasets.json
  annual_max(...)  per synthetic year, the highest wind any track point produced at the location — the modified
                   Rankine vortex of the calibrated storm channel (ml.scoring.storm_physics), within 400 km
                   (ml.scoring.storm_return_level.INFLUENCE_KM); basins are independent simulations, so a location
                   reached from two basins takes the higher of the two in each year
  rows(...)        the storm_v4_wind layer's rows for a location: the return level at each registered return period,
                   the empirical (1 − 1/T) quantile of the 10,000 annual maxima (a quiet year counts as zero)"""
from __future__ import annotations

import hashlib
import json
import logging
from functools import lru_cache

import numpy as np

from services.loss import registry

log = logging.getLogger(__name__)
ROOT = registry.ROOT
OUT = ROOT / "data" / "datasets" / "storm_v4"
BASINS = ("EP", "NA", "NI", "SI", "SP", "WP")
FIELDS = ("gyear", "tc", "lat", "lon", "vmax", "rmw")
YEARS = 10_000


def _src() -> dict:
    return registry.event_sets()["storm_v4"]


def compact() -> dict:
    """Read the published files once into per-basin arrays; record each array file's size and sha-256."""
    import pandas as pd
    E = _src()
    src_dir = ROOT / E["files"]["dir"]
    cols = E["columns"]
    OUT.mkdir(parents=True, exist_ok=True)
    record = {}
    for basin in BASINS:
        parts = []
        for idx in range(E["files"]["per_basin"]):
            f = src_dir / E["files"]["pattern"].format(basin=basin, index=idx)
            df = pd.read_csv(f, header=None, names=cols, usecols=["year", "tc_number", "lat", "lon_0_360", "max_wind_ms",
                                                                  "rmw_km"], dtype="float64")
            df["gyear"] = idx * E["files"]["years_per_file"] + df["year"].astype("int64")
            parts.append(df)
        df = pd.concat(parts, ignore_index=True)
        lon = df["lon_0_360"].to_numpy()
        arr = {"gyear": df["gyear"].to_numpy(np.int32), "tc": df["tc_number"].to_numpy(np.int16),
               "lat": df["lat"].to_numpy(np.float32), "lon": np.where(lon > 180.0, lon - 360.0, lon).astype(np.float32),
               "vmax": df["max_wind_ms"].to_numpy(np.float32), "rmw": df["rmw_km"].to_numpy(np.float32)}
        order = np.argsort(arr["lat"], kind="stable")
        arr = {k: v[order] for k, v in arr.items()}
        if int(arr["gyear"].max()) >= YEARS:
            raise ValueError(f"{basin}: a synthetic year beyond {YEARS}")
        out = OUT / f"{basin}.npz"
        tmp = out.with_suffix(".part.npz")
        np.savez(tmp, **arr)
        tmp.replace(out)
        record[basin] = {"file": str(out.relative_to(ROOT)), "bytes": out.stat().st_size,
                         "sha256": hashlib.sha256(out.read_bytes()).hexdigest(), "track_points": int(arr["lat"].size)}
        log.info("%s: %d track points", basin, arr["lat"].size)
    _basins.cache_clear()
    from scripts.fetch_supply_datasets import record as record_entry
    record_entry("storm_v4_compact", {"source": "derived from the event set storm_v4 (data/reference/event_sets.json) by "
                                                "services.loss.storm_events.compact", "licence": E["licence"],
                                      "version": E["version"], "files": list(record.values())})
    return record


@lru_cache(maxsize=1)
def _basins() -> dict[str, dict[str, np.ndarray]]:
    out = {}
    for b in BASINS:
        f = OUT / f"{b}.npz"
        if f.exists():
            z = np.load(f)
            out[b] = {k: z[k] for k in FIELDS}
    return out


def held() -> bool:
    return len(_basins()) == len(BASINS)


def annual_max(lat: float, lon: float) -> np.ndarray:
    """The highest wind (m/s) any synthetic track produced at the point in each of the 10,000 years."""
    from ml.scoring.storm_physics import wind_field
    from ml.scoring.storm_return_level import BBOX_DEG, INFLUENCE_KM, _haversine
    out = np.zeros(YEARS, dtype=np.float64)
    for b in _basins().values():
        lo, hi = np.searchsorted(b["lat"], [lat - BBOX_DEG, lat + BBOX_DEG])
        if hi <= lo:
            continue
        sl = slice(lo, hi)
        dlon = (b["lon"][sl] - lon + 180.0) % 360.0 - 180.0
        near = np.abs(dlon) <= BBOX_DEG
        if not near.any():
            continue
        la, ln = b["lat"][sl][near].astype(np.float64), b["lon"][sl][near].astype(np.float64)
        d = _haversine(lat, lon, la, ln)
        keep = d <= INFLUENCE_KM
        if not keep.any():
            continue
        wind = wind_field(b["vmax"][sl][near][keep], d[keep], b["rmw"][sl][near][keep])
        np.maximum.at(out, b["gyear"][sl][near][keep], wind)
    return out


def rows(lat: float, lon: float, _tiles=None) -> list[dict]:
    import h3
    L = registry.layer("storm_v4_wind")
    base = {"layer_key": "storm_v4_wind", "layer_version": L["version"], "latitude": lat, "longitude": lon,
            "h3_cell": h3.latlng_to_cell(lat, lon, 8), "cell_fraction": None, "cell_mean": None}
    if not held():
        return []                                   # the compact event set is not built: nothing is recorded
    am = annual_max(lat, lon)
    return [{**base, "rp_years": rp, "status": "sampled", "value": float(np.quantile(am, 1.0 - 1.0 / rp))}
            for rp in L["return_periods"]]


def manifest() -> dict:
    return json.loads((ROOT / "data" / "reference" / "supply_datasets.json").read_text()).get("storm_v4_compact", {})
