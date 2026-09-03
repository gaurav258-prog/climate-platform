"""Regional (ocean-dynamic) sea-level offset — the local deviation of sea level from the global mean.

Global-mean AR6 SLR (ml/scoring/sea_level.py) is the same number everywhere; real coasts differ from it by
a spatial pattern. The largest spatially-varying, obtainable piece is the OCEAN-DYNAMIC component — how ocean
circulation and steric changes redistribute sea level — captured by the CMIP6 variable `zos` (sea-surface
height above geoid). This module reads the ensemble `zos`-change field built by scripts/build_cmip6_zos.py and
returns, per location × scenario × horizon, the metres by which local sea level rises MORE (+) or LESS (−) than
the global mean.

Honest scope: this is the ocean-dynamic term ONLY. The gravitational 'fingerprint' of ice-mass loss and glacial
isostatic adjustment are the disclosed remainder — the full IPCC AR6 regional field (a bounded data follow-on).
Returns 0.0 (→ falls back to global-mean) when the field isn't built, the scenario has no CMIP6 mapping
(baseline/current), or no ocean cell is near the point.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

import numpy as np

NPZ = "data/cmip6/cmip6_zos_regional.npz"
SCENARIO_TO_SSP = {"orderly_1_5c": "ssp126", "disorderly_2c": "ssp245", "hot_house_3_5c": "ssp585"}
HORIZON_TO_PERIOD = {"2030": "2021-2040", "2050": "2041-2060", "2100": "2081-2100"}
OFFSET_CAP_M = 0.6          # guard against extreme near-coast model artefacts (disclosed clamp)
SEARCH_DEG = 6.0           # look this far for the nearest ocean cell to a coastal point


@lru_cache(maxsize=1)
def _field() -> Optional[dict]:
    if not os.path.exists(NPZ):
        return None
    return dict(np.load(NPZ))


def has_field() -> bool:
    return _field() is not None


def regional_dynamic_offset_m(lat: float, lon: float, scenario: str, horizon: str) -> float:
    """Ocean-dynamic local-minus-global-mean SLR in metres for (lat, lon) under scenario × horizon.
    0.0 when unmapped / field missing / no nearby ocean cell — so the caller keeps the global-mean rise."""
    ssp = SCENARIO_TO_SSP.get(scenario)
    per = HORIZON_TO_PERIOD.get(horizon)
    f = _field()
    if not (ssp and per) or f is None:
        return 0.0
    key = f"{ssp}|{per}|dzos_mean"
    if key not in f:
        return 0.0
    arr = f[key]                     # (nlat, nlon), NaN over land
    lats = f["lat"]; lons = f["lon"]
    j = int(np.abs(lats - lat).argmin())
    i = int(np.abs(lons - lon).argmin())
    if np.isfinite(arr[j, i]):
        return float(np.clip(arr[j, i], -OFFSET_CAP_M, OFFSET_CAP_M))
    # coastal point may land on a masked (land) grid cell — take the nearest ocean cell within SEARCH_DEG
    dlat = float(lats[1] - lats[0]); dlon = float(lons[1] - lons[0])
    rj = max(1, int(SEARCH_DEG / abs(dlat))); ri = max(1, int(SEARCH_DEG / abs(dlon)))
    best = None; bestd = 1e9
    for jj in range(max(0, j - rj), min(len(lats), j + rj + 1)):
        for ii in range(max(0, i - ri), min(len(lons), i + ri + 1)):
            v = arr[jj, ii]
            if np.isfinite(v):
                d = (lats[jj] - lat) ** 2 + (lons[ii] - lon) ** 2
                if d < bestd:
                    bestd = d; best = v
    if best is None:
        return 0.0
    return float(np.clip(best, -OFFSET_CAP_M, OFFSET_CAP_M))
