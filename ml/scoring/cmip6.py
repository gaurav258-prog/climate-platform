"""Raw multi-model CMIP6 delta lookup (projections v3).

The bridge between the ensemble deltas built by scripts/build_cmip6_deltas.py and the hazard
scorers. Our UI scenario × horizon axis maps to a CMIP6 (SSP, time-period): we let the MODELS set
the actual regional warming and precipitation change, instead of the parametric global-delta ×
latitude-amplification and the single Mediterranean precip coefficient.

  orderly_1_5c → SSP1-2.6      2030 → 2021-2040
  disorderly_2c → SSP2-4.5     2050 → 2041-2060
  hot_house_3_5c → SSP5-8.5    2100 → 2081-2100

`baseline` and `current` have no CMIP6 mapping (baseline's ~0.6 °C is below any SSP end-century
pathway, current is 0) — those fall back to the parametric model, as does any belt not in the
built delta table. Returns None in those cases so the caller keeps its parametric path.
"""
from __future__ import annotations

import csv
import os
from functools import lru_cache
from typing import NamedTuple, Optional

DELTAS_CSV = "data/cmip6/cmip6_deltas.csv"

SCENARIO_TO_SSP = {"orderly_1_5c": "ssp126", "disorderly_2c": "ssp245", "hot_house_3_5c": "ssp585"}
HORIZON_TO_PERIOD = {"2030": "2021-2040", "2050": "2041-2060", "2100": "2081-2100"}


class Cmip6Delta(NamedTuple):
    dtas_c: float        # ensemble-mean warming °C (future period − 1995-2014 baseline)
    dpr_frac: float      # ensemble-mean fractional precip change (negative = drier)
    n_models: int        # ensemble size behind these means
    dtas_std_c: float    # across-model spread (°C) — an honest uncertainty input
    dpr_std: float       # across-model spread (fractional precip)
    dwind_frac: float = float("nan")   # ensemble-mean fractional near-surface wind change (NaN if wind field not built)
    dwind_std: float = float("nan")    # across-model spread (fractional wind)


@lru_cache(maxsize=1)
def _table() -> dict:
    out: dict = {}
    if not os.path.exists(DELTAS_CSV):
        return out
    with open(DELTAS_CSV) as f:
        for r in csv.DictReader(f):
            out[(r["region"], r["ssp"], r["period"])] = Cmip6Delta(
                float(r["dtas_mean_c"]), float(r["dpr_frac_mean"]), int(r["n_models"]),
                float(r["dtas_std_c"]), float(r["dpr_frac_std"]))
    return out


def cmip6_delta(region_key: Optional[str], scenario: str, horizon: str) -> Optional[Cmip6Delta]:
    """CMIP6 ensemble delta for a belt under a scenario × horizon, or None when CMIP6 doesn't
    cover the combo (baseline/current, or a region not in the built table)."""
    ssp = SCENARIO_TO_SSP.get(scenario)
    per = HORIZON_TO_PERIOD.get(horizon)
    if not (ssp and per and region_key):
        return None
    return _table().get((region_key, ssp, per))


def has_coverage() -> bool:
    return bool(_table())


# ── global (lat/lon) delta field — the worldwide analogue of the belt table ──────────────────────
GLOBAL_NPZ = "data/cmip6/cmip6_global_deltas.npz"
WIND_NPZ = "data/cmip6/cmip6_wind_deltas.npz"   # separate sfcWind field (build_cmip6_wind.py), co-registered 2° grid


@lru_cache(maxsize=1)
def _global():
    """Lazy-load the global 2° delta field (built by scripts/build_cmip6_global.py). Returns a dict
    with 'lat','lon','n_models' and per-(ssp,period) mean/std arrays, or None if not built yet."""
    if not os.path.exists(GLOBAL_NPZ):
        return None
    import numpy as np
    z = np.load(GLOBAL_NPZ)
    return {k: z[k] for k in z.files}


@lru_cache(maxsize=1)
def _wind():
    """Lazy-load the global 2° near-surface wind-change field (build_cmip6_wind.py). Same grid as _global().
    Returns the dict or None if not built yet — an older deployment without it simply reports wind as NaN."""
    if not os.path.exists(WIND_NPZ):
        return None
    import numpy as np
    z = np.load(WIND_NPZ)
    return {k: z[k] for k in z.files}


def cmip6_delta_latlon(lat: Optional[float], lon: Optional[float],
                       scenario: str, horizon: str) -> Optional[Cmip6Delta]:
    """CMIP6 ensemble delta at an arbitrary location (nearest 2° grid cell), for worldwide assets that
    aren't on a named belt. None where CMIP6 doesn't cover the combo (baseline/current), the field
    isn't built, or the nearest cell is NaN (e.g. a precip-fraction over desert / ocean gap)."""
    ssp = SCENARIO_TO_SSP.get(scenario)
    per = HORIZON_TO_PERIOD.get(horizon)
    g = _global()
    if not (ssp and per and g is not None and lat is not None and lon is not None):
        return None
    key = f"{ssp}|{per}"
    if f"{key}|dtas_mean" not in g:
        return None
    import numpy as np
    i = int(np.abs(g["lat"] - float(lat)).argmin())
    j = int(np.abs(g["lon"] - float(lon)).argmin())
    dtas = float(g[f"{key}|dtas_mean"][i, j])
    dtas_std = float(g[f"{key}|dtas_std"][i, j])
    dpr = g[f"{key}|dpr_mean"][i, j] if f"{key}|dpr_mean" in g else np.nan
    dpr_std = g[f"{key}|dpr_std"][i, j] if f"{key}|dpr_std" in g else np.nan
    if np.isnan(dtas):
        return None
    dpr = 0.0 if (dpr is None or np.isnan(dpr)) else float(dpr)          # temp always defined; precip
    dpr_std = 0.0 if (dpr_std is None or np.isnan(dpr_std)) else float(dpr_std)  # frac may be NaN (desert)

    # near-surface wind change from the co-registered wind field (same 2° grid), NaN if not built / gap
    dwind = dwind_std = float("nan")
    w = _wind()
    wkey = f"{key}|dwind_mean"
    if w is not None and wkey in w:
        wi = int(np.abs(w["lat"] - float(lat)).argmin())
        wj = int(np.abs(w["lon"] - float(lon)).argmin())
        wv = float(w[wkey][wi, wj])
        if not np.isnan(wv):
            dwind = wv
            dwind_std = float(w[f"{key}|dwind_std"][wi, wj])
    return Cmip6Delta(dtas, dpr, int(g["n_models"]), dtas_std, dpr_std, dwind, dwind_std)
