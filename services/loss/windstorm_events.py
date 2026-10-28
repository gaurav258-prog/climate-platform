"""The PRIMAVERA European winter windstorm event set (the product owner's decisions of 2026-10-25): the 72-hour maximum
3-second gust footprint of every winter storm in 21 climate-model runs (data/reference/event_sets.json
'primavera_windstorm'), held as one array of winter maxima, and the gust each location should expect at a return period.

  compact()      the published archives → per run and winter, the highest gust any footprint of that winter holds at each
                 grid point (a point no footprint of the winter reaches counts as zero, as a quiet year does for the
                 cyclone maps); the winters of all runs together (1,332) → the return level at each registered return
                 period, the empirical (1 − 1/T) quantile per grid point — the method of the cyclone maps
                 (services.loss.storm_events). One file under data/datasets/primavera_windstorm/compact, its checksum
                 recorded in data/reference/supply_datasets.json
  rows(...)      the primavera_windstorm_gust layer's rows for a location: the grid cell holding it (its published
                 bounds); outside the grid, 'outside_coverage'

Footprints are read as published: every footprint of a winter's archive counts for that winter, its file name naming the
winter. A footprint holds −1 (its only negative value) at the grid points it does not hold — 'the grid points assigned to
other cyclones masked out' (the event set's documentation, Footprint contamination); any other negative value stops the
build. The archives are read in place, never unpacked, by a process started from outside their folder."""
from __future__ import annotations

import hashlib
import logging
import re
import tarfile
from functools import lru_cache
from typing import Optional

import numpy as np

from services.loss import registry

log = logging.getLogger(__name__)
ROOT = registry.ROOT
KEY = "primavera_windstorm"                  # the event set
LAYER = "primavera_windstorm_gust"           # the gust maps derived from it
NOT_HELD = -1.0                              # a footprint's value at a grid point another storm holds
COMPACT = ROOT / "data" / "datasets" / "primavera_windstorm" / "compact" / "winter_max.npz"
_WINTER = re.compile(r"_winter(\d{4})-(\d{4})_")
_DATE = re.compile(r"_(\d{4})-(\d{2})-(\d{2})_regrid_corrected\.nc$")


def _set() -> dict:
    return registry.event_sets()[KEY]


def _footprints(run: str):
    """(file name, gust array, latitude, longitude, bounds, licence attribute) of every footprint in one run's archive,
    read in place; a grid point the footprint does not hold is NaN."""
    import netCDF4
    E = _set()
    outer = tarfile.open(ROOT / E["files"]["archives"] / f"{run}.tar")
    inner_name = E["files"]["inner"].format(run=run)
    inner = tarfile.open(fileobj=outer.extractfile(inner_name), mode="r|gz")
    for m in inner:
        if not (m.isfile() and m.name.endswith(".nc")):
            continue
        name = m.name.rsplit("/", 1)[-1]
        d = netCDF4.Dataset("footprint", memory=inner.extractfile(m).read())
        try:
            v = d.variables[E["variable"]]
            if v.getncattr("units") != E["units"]:
                raise ValueError(f"{name}: units {v.getncattr('units')!r}, not {E['units']!r}")
            g = np.ma.filled(v[:].astype(np.float32), np.nan)
            if (g[g < 0] != NOT_HELD).any():
                raise ValueError(f"{name}: a negative gust other than the not-held marker {NOT_HELD}")
            g[g == NOT_HELD] = np.nan
            yield (name, g, d.variables["latitude"][:].data, d.variables["longitude"][:].data,
                   d.variables["latitude_bnds"][:].data, d.variables["longitude_bnds"][:].data,
                   d.getncattr("license") if "license" in d.ncattrs() else None)
        finally:
            d.close()


def compact() -> dict:
    """Build the winter maxima and the return levels from the published archives; record the file's checksum."""
    E = _set()
    L = registry.layer(LAYER)
    maxima, labels, runs, grid, counts = [], [], [], None, {}
    for run in E["runs"]:
        by_winter: dict[str, np.ndarray] = {}
        n, outside_season, licences = 0, 0, set()
        for name, g, lat, lon, lat_b, lon_b, lic in _footprints(run):
            licences.add(lic)
            if grid is None:
                grid = (lat, lon, lat_b, lon_b)
            elif not (np.array_equal(grid[0], lat) and np.array_equal(grid[1], lon)):
                raise ValueError(f"{name}: a grid other than the first footprint's")
            w = _WINTER.search(name)
            if w is None:
                raise ValueError(f"{name}: no winter in the file name")
            label = f"{w.group(1)}/{w.group(2)}"
            month = int(_DATE.search(name).group(2))
            outside_season += month not in (10, 11, 12, 1, 2, 3)
            cur = by_winter.get(label)
            by_winter[label] = g if cur is None else np.fmax(cur, g)
            n += 1
        for label in sorted(by_winter):
            maxima.append(np.nan_to_num(by_winter[label], nan=0.0))   # no footprint reached the point: a quiet winter
            labels.append(label)
            runs.append(run)
        counts[run] = {"footprints": n, "winters": len(by_winter), "central_date_outside_oct_mar": outside_season,
                       "file_licence_attribute": sorted(x for x in licences if x)}
        log.info("%s: %d footprints, %d winters", run, n, len(by_winter))
    am = np.stack(maxima).astype(np.float32)
    if am.shape[0] != E["years_simulated"]:
        raise ValueError(f"{am.shape[0]} winters held, the event set states {E['years_simulated']}")
    rps = L["return_periods"]
    levels = np.stack([np.quantile(am, 1.0 - 1.0 / rp, axis=0) for rp in rps]).astype(np.float32)
    COMPACT.parent.mkdir(parents=True, exist_ok=True)
    tmp = COMPACT.with_name("winter_max.part.npz")
    np.savez_compressed(tmp, winter_max=am, winter=np.array(labels), run=np.array(runs), rp_years=np.array(rps),
                        rp_level=levels, latitude=grid[0], longitude=grid[1], latitude_bnds=grid[2],
                        longitude_bnds=grid[3])
    tmp.replace(COMPACT)
    _held.cache_clear()
    record = {"file": str(COMPACT.relative_to(ROOT)) if COMPACT.is_relative_to(ROOT) else str(COMPACT),
              "bytes": COMPACT.stat().st_size,
              "sha256": hashlib.sha256(COMPACT.read_bytes()).hexdigest(), "winters": int(am.shape[0]),
              "grid": [int(am.shape[1]), int(am.shape[2])], "runs": counts}
    from scripts.fetch_supply_datasets import record as record_entry
    record_entry(f"{KEY}_compact", {"source": f"derived from the event set {KEY} (data/reference/event_sets.json) by "
                                              "services.loss.windstorm_events.compact",
                                    "licence": E["licence"], "version": E["version"], "files": [record]})
    return record


@lru_cache(maxsize=1)
def _held() -> Optional[dict]:
    if not COMPACT.exists():
        return None
    z = np.load(COMPACT)
    return {k: z[k] for k in ("rp_years", "rp_level", "latitude_bnds", "longitude_bnds")}


def held() -> bool:
    return _held() is not None


def cell(lat: float, lon: float) -> Optional[tuple[int, int]]:
    """(row, column) of the grid cell whose published bounds hold the location, or None outside the grid."""
    h = _held()
    lb, ob = h["latitude_bnds"], h["longitude_bnds"]
    rows = np.nonzero((np.minimum(lb[:, 0], lb[:, 1]) <= lat) & (lat < np.maximum(lb[:, 0], lb[:, 1])))[0]
    cols = np.nonzero((np.minimum(ob[:, 0], ob[:, 1]) <= lon) & (lon < np.maximum(ob[:, 0], ob[:, 1])))[0]
    if not (len(rows) and len(cols)):
        return None
    return int(rows[0]), int(cols[0])


def rows(lat: float, lon: float, _tiles=None) -> list[dict]:
    """The layer's rows for one location: the return level of its grid cell at each registered return period."""
    import h3
    L = registry.layer(LAYER)
    base = {"layer_key": LAYER, "layer_version": L["version"], "latitude": lat, "longitude": lon,
            "h3_cell": h3.latlng_to_cell(lat, lon, 8), "cell_fraction": None, "cell_mean": None}
    h = _held()
    if h is None:
        return []                                   # the compact event set is not built: nothing is recorded
    if [int(r) for r in h["rp_years"]] != list(L["return_periods"]):
        raise registry.RegistryError(f"{LAYER}: the built return periods are not the registered ones")
    rc = cell(lat, lon)
    if rc is None:
        return [{**base, "rp_years": rp, "status": "outside_coverage", "value": None} for rp in L["return_periods"]]
    i, j = rc
    return [{**base, "rp_years": int(rp), "status": "sampled", "value": float(h["rp_level"][k, i, j])}
            for k, rp in enumerate(h["rp_years"])]


def manifest() -> dict:
    import json
    return json.loads((ROOT / "data" / "reference" / "supply_datasets.json").read_text()).get(f"{KEY}_compact", {})
