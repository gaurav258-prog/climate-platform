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
