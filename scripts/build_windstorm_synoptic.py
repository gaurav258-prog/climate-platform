"""SYNOPTIC extreme-wind climatology — the windstorm field with convective and tropical hours removed.

Both earlier windstorm fields failed the independent NOAA Storm-Events backtest (annual-max gust ρ ≤ 0.20): the
annual-maximum 10 m gust in ERA5 is set by thunderstorm outflow and tropical cyclones, not by the synoptic
windstorm peril the channel represents (extratropical cyclones, downslope and gap winds, blizzards). This builder
removes those hours by their physical signature rather than by season or tuning:
  • convective hours: ERA5 CAPE at the cell ≥ CAPE_MAX J/kg at that hour (a thunderstorm environment);
  • tropical hours: the cell lies within TC_RADIUS_KM of an IBTrACS track point within ±TC_HOURS of the hour.
The per-cell annual maximum of what remains — the synoptic gust — is reduced to a Gumbel 50-year return level and
mean annual max, as before. Hourly ERA5 (i10fg + cape) per year, reduced locally, raw discarded; resumable.

Run: PYTHONPATH=. .venv/bin/python scripts/build_windstorm_synoptic.py conus [--years 2009-2013]
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

from core.config import settings

REGIONS = {"conus": {"area": [50, -125, 24, -66], "dir": "data/wind/synoptic_conus", "out": "data/wind/windstorm_synoptic_conus.npz"}}
GRID = [0.5, 0.5]
CAPE_MAX = 300.0        # J/kg — below this the boundary layer cannot sustain deep convection
TC_RADIUS_KM = 500.0
TC_HOURS = 6
_HOURS = [f"{h:02d}:00" for h in range(24)]


def _tc_mask(times, lat, lon) -> np.ndarray:
    """True where an hour×cell is inside a tropical cyclone's reach (IBTrACS in storm_events)."""
    from sqlalchemy import text

    from core.db.session import get_session
    from services.intelligence.model_validation import _hav_vec
    t0, t1 = str(times[0])[:19], str(times[-1])[:19]
    with get_session() as s:
        rows = s.execute(text("""SELECT observation_time, CAST(lat AS FLOAT), CAST(lon AS FLOAT) FROM storm_events
                                 WHERE observation_time BETWEEN CAST(:a AS timestamptz) - interval '12 hours' AND CAST(:b AS timestamptz) + interval '12 hours'
                                   AND lat BETWEEN :la0 AND :la1 AND lon BETWEEN :lo0 AND :lo1"""),
                         {"a": t0, "b": t1, "la0": float(lat.min()) - 5, "la1": float(lat.max()) + 5,
                          "lo0": float(lon.min()) - 5, "lo1": float(lon.max()) + 5}).all()
    mask = np.zeros((len(times), len(lat), len(lon)), dtype=bool)
    if not rows:
        return mask
    tt = np.asarray(times).astype("datetime64[h]").astype("int64")
    LON, LAT = np.meshgrid(lon, lat)
    for ot, la, lo in rows:
        near = _hav_vec(la, lo, LAT.ravel(), LON.ravel()).reshape(LAT.shape) <= TC_RADIUS_KM
        h = np.datetime64(ot.replace(tzinfo=None), "h").astype("int64")
        i0, i1 = np.searchsorted(tt, h - TC_HOURS), np.searchsorted(tt, h + TC_HOURS, side="right")
        mask[i0:i1] |= near
    return mask


def _retrieve(c, req: dict, target: str, wait_s: int = 300) -> None:
    """CDS caps the number of queued requests per user; a rejected submission is retried after a wait, not fatal."""
    import time
    while True:
        try:
            c.retrieve("reanalysis-era5-single-levels", req, target)
            return
        except Exception as e:                            # "The job has been rejected … queued requests … limited"
            if "rejected" not in str(e).lower() and "limited" not in str(e).lower():
                raise
            print(f"  CDS queue full, retrying in {wait_s // 60} min", flush=True)
            time.sleep(wait_s)


def _year(c, region: dict, year: int) -> str:
    npy = f"{region['dir']}/annmax_{year}.npy"
    if os.path.exists(npy):
        return npy
    # one request per variable: a two-variable hourly year exceeds the CDS field limit
    raw = {}
    # gust must be hourly (the maximum is an hourly quantity); CAPE describes the convective ENVIRONMENT, which
    # persists for hours, so 3-hourly sampling is enough to flag a thunderstorm environment and cuts the queue time
    for var, key, hours in (("instantaneous_10m_wind_gust", "gust", _HOURS), ("convective_available_potential_energy", "cape", _HOURS[::3])):
        raw[key] = f"/tmp/era5_syn_{year}_{key}.nc"
        if not os.path.exists(raw[key]):
            _retrieve(c, {"product_type": "reanalysis", "variable": [var], "year": str(year),
                          "month": [f"{m:02d}" for m in range(1, 13)], "day": [f"{d:02d}" for d in range(1, 32)],
                          "time": hours, "grid": GRID, "data_format": "netcdf", "area": region["area"]}, raw[key])
    import xarray as xr
    g = xr.open_dataset(raw["gust"]); cp = xr.open_dataset(raw["cape"])
    tname = [d for d in g["i10fg"].dims if d not in ("latitude", "longitude")][0]
    cp = cp.reindex({tname: g[tname]}, method="nearest")      # each gust hour takes the nearest 3-hourly CAPE
    ds = xr.merge([g, cp])
    tdim = [d for d in ds["i10fg"].dims if d not in ("latitude", "longitude")][0]
    gust = ds["i10fg"].transpose(tdim, "latitude", "longitude").values
    cape = ds["cape"].transpose(tdim, "latitude", "longitude").values
    lat, lon, times = ds["latitude"].values, ds["longitude"].values, ds[tdim].values
    ds.close(); [os.remove(f) for f in raw.values()]
    conv = cape >= CAPE_MAX
    tc = _tc_mask(times, lat, lon)
    syn = np.where(conv | tc, np.nan, gust)
    ann = np.nanmax(syn, axis=0).astype("float32")
    np.save(npy, ann)
    if not os.path.exists(f"{region['dir']}/_grid.npz"):
        np.savez(f"{region['dir']}/_grid.npz", lat=lat, lon=lon)
    print(f"  {year}: synoptic annual-max gust p50={np.nanpercentile(ann, 50):.1f} max={np.nanmax(ann):.1f} m/s · "
          f"hours removed: convective {100 * conv.mean():.1f}% tropical {100 * tc.mean():.2f}%", flush=True)
    return npy


def _gumbel(annmax: np.ndarray, T: float = 50.0) -> np.ndarray:
    beta = np.nanstd(annmax, axis=0) * np.sqrt(6.0) / np.pi
    return np.nanmean(annmax, axis=0) - 0.5772 * beta - beta * np.log(-np.log(1.0 - 1.0 / T))


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("region", nargs="?", default="conus"); ap.add_argument("--years", default="2009-2023")
    ap.add_argument("--reduce-only", action="store_true"); a = ap.parse_args()
    region = REGIONS[a.region]; os.makedirs(region["dir"], exist_ok=True)
    y0, y1 = (int(x) for x in a.years.split("-"))
    if not a.reduce_only:
        import cdsapi
        c = cdsapi.Client(url=settings.CDSAPI_URL, key=settings.CDSAPI_KEY, quiet=True)
        for y in range(y0, y1 + 1):
            _year(c, region, y)
    paths = sorted(p for p in os.listdir(region["dir"]) if p.startswith("annmax_") and y0 <= int(p[7:11]) <= y1)
    if not paths:
        return 0
    stack = np.stack([np.load(f"{region['dir']}/{p}") for p in paths]); grid = np.load(f"{region['dir']}/_grid.npz")
    np.savez_compressed(region["out"], lat=grid["lat"], lon=grid["lon"], gust_ms=_gumbel(stack).astype("float32"),
                        mean_annual_max=np.nanmean(stack, axis=0).astype("float32"), n_years=len(paths), years=[int(p[7:11]) for p in paths])
    print(f"saved {region['out']} from {len(paths)} years")
    return 0


if __name__ == "__main__":
    sys.exit(main())
