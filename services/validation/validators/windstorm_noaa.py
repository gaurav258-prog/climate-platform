"""Windstorm validator — the synoptic extreme-gust field against NOAA Storm Events observed non-convective wind
(High Wind / Strong Wind / Blizzard / Dust Storm, continental US 2015–2023; scripts/backtest_windstorm_noaa.py holds
the geolocation logic, reused here).

Field under test: data/wind/windstorm_synoptic_conus.npz (scripts/build_windstorm_synoptic.py — hourly ERA5 gust with
convective hours (CAPE ≥ 300 J/kg) and tropical-cyclone hours (IBTrACS within 500 km) removed, 2014–2023, reduced to
a Gumbel 50-year return level and the mean annual maximum). Predicted = the return level (what the channel would
publish); observed = the peak reported gust per 0.5° cell over ≥ 3 events. `rank` kind. Result 2026-09-12: ρ 0.22
(the unfiltered annual-max field scored 0.08 on the same target; mean annual max 0.26) — three times the skill,
still below the 0.35 gate on every target variant tried (median, p90, ≥10 events, measured-only reports). Indicator.
"""
from __future__ import annotations

import glob
from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session

from services.validation.engine import ValidationResult, register

GRID = Path("data/wind/windstorm_synoptic_conus.npz")
MIN_EVENTS = 3


def _run(session: Session) -> ValidationResult:
    import pandas as pd
    from scipy.stats import spearmanr

    from scripts.backtest_windstorm_noaa import (
        _ABBR,
        CONUS,
        FILES,
        KT_TO_MS,
        WINDSTORM_TYPES,
        _zone_centroids,
    )
    if not GRID.exists() or not glob.glob(FILES):
        return ValidationResult(hazard_type="windstorm", kind="rank", predicted=[], observed=[], labels=[],
                                target_source="NOAA Storm Events non-convective wind, CONUS 2015–2023", scope="US", method="out_of_sample",
                                notes="synoptic field or NOAA Storm Events files missing (scripts/build_windstorm_synoptic.py, data/windstorm_val)")
    zc = _zone_centroids()
    df = pd.concat([pd.read_csv(f, low_memory=False, compression="gzip",
                                usecols=["EVENT_TYPE", "STATE", "CZ_FIPS", "BEGIN_LAT", "BEGIN_LON", "MAGNITUDE"]) for f in sorted(glob.glob(FILES))],
                   ignore_index=True)
    df = df[df.EVENT_TYPE.isin(WINDSTORM_TYPES)].copy()

    def loc(r):
        if pd.notna(r.BEGIN_LAT) and pd.notna(r.BEGIN_LON):
            return r.BEGIN_LAT, r.BEGIN_LON
        c = zc.get((_ABBR.get(str(r.STATE).upper()), int(r.CZ_FIPS)) if pd.notna(r.CZ_FIPS) else None)
        return (c[0], c[1]) if c else (np.nan, np.nan)
    df[["lat", "lon"]] = df.apply(lambda r: pd.Series(loc(r)), axis=1)
    df = df.dropna(subset=["lat", "lon", "MAGNITUDE"]); df = df[(df.MAGNITUDE > 0) & df.lat.between(*CONUS[:2]) & df.lon.between(*CONUS[2:])]
    z = np.load(GRID); glat, glon, rl, am = z["lat"], z["lon"], z["gust_ms"], z["mean_annual_max"]
    gi = np.abs(glat[:, None] - df.lat.values).argmin(axis=0); gj = np.abs(glon[:, None] - df.lon.values).argmin(axis=0)
    pc = pd.DataFrame({"gi": gi, "gj": gj, "kt": df.MAGNITUDE.values}).groupby(["gi", "gj"]).agg(obs=("kt", "max"), n=("kt", "size")).reset_index()
    pc = pc[pc.n >= MIN_EVENTS]
    pred = [float(rl[int(i), int(j)]) for i, j in zip(pc.gi, pc.gj)]
    pred_am = [float(am[int(i), int(j)]) for i, j in zip(pc.gi, pc.gj)]
    obs = (pc.obs * KT_TO_MS).tolist()
    return ValidationResult(hazard_type="windstorm", kind="rank", predicted=pred, observed=obs, labels=[f"{float(glat[int(i)]):.2f},{float(glon[int(j)]):.2f}" for i, j in zip(pc.gi, pc.gj)],
                            target_source="NOAA Storm Events observed peak gust, non-convective wind types, CONUS 2015–2023", scope="US", method="out_of_sample",
                            data_vintage=f"synoptic ERA5 gust {int(z['n_years'])} yrs vs NOAA 2015–2023",
                            notes=(f"synoptic 50-yr return level (convective and tropical hours removed) vs observed peak gust per 0.5° cell (≥{MIN_EVENTS} events); "
                                   f"mean-annual-max variant ρ {spearmanr(pred_am, obs)[0]:.3f}; the unfiltered annual-max field scored 0.08 on this target"),
                            extra={"rho_mean_annual_max": round(float(spearmanr(pred_am, obs)[0]), 4), "n_years": int(z["n_years"])})


register("windstorm_noaa")(_run)
