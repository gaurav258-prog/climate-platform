"""Forward projection of the severe-convective-storm ENVIRONMENT (the Solvency II 'hail' peril).

What moves is instability. IPCC AR6 WGI §11.7.3.5 gives high confidence that CAPE increases with warming, and
Romps (2016) gives the rate: about 6%–7% per kelvin of surface warming. The convective-potential index is the
WMAXSHEAR form sqrt(2·CAPE) × shear, so a CAPE factor (1+r)^ΔT moves the index by (1+r)^(ΔT/2). Shear stays at
today's climatology (AR6: no robust shear change). ΔT is the cell's own CMIP6 ensemble-mean warming, and the
across-model spread × the 6–7% range gives the band. The projected index is read through the same NOAA SPC anchor
as today's score, so the score stays an annual probability of a damaging event.

What does NOT move: event frequency is never scaled directly (AR6: low confidence in event projections from
environments), hail size is not projected, and a cell already where the SPC-fitted probability stops rising stays
there. Every number comes from data/reference/severe_convective_projection.json, with its source.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import NamedTuple, Optional

from ml.scoring.cmip6 import Cmip6Delta

REFERENCE = "data/reference/severe_convective_projection.json"


@lru_cache(maxsize=1)
def reference() -> dict:
    with open(REFERENCE) as f:
        return json.load(f)


def cape_rates() -> tuple[float, float, float]:
    """(low, central, high) fractional CAPE change per kelvin — central is the midpoint of the cited range."""
    r = reference()["mechanism"]["cape_rate_per_k"]
    return r["low"], (r["low"] + r["high"]) / 2.0, r["high"]


def index_factor(dtas_c: float, rate: float) -> float:
    """Multiplier on the convective-potential index for a local warming of dtas_c at a CAPE rate per kelvin."""
    return (1.0 + rate) ** (reference()["mechanism"]["index_exponent_on_cape"] * dtas_c)


class ProjectedPotential(NamedTuple):
    central: float
    lower: Optional[float]      # None = no honest band (no CMIP6 spread)
    upper: Optional[float]
    dtas_c: Optional[float]     # None = not projected (baseline / current / no CMIP6 cover)


def project_potential(potential: float, delta: Optional[Cmip6Delta]) -> ProjectedPotential:
    """Today's 0–100 potential carried to a scenario × horizon. Unchanged when there is no CMIP6 delta.
    Not capped at 100: the anchor is flat beyond its last point, so a value past the grid reads as its top."""
    if delta is None:
        return ProjectedPotential(potential, None, None, None)
    lo_r, mid_r, hi_r = cape_rates()
    central = potential * index_factor(delta.dtas_c, mid_r)
    if delta.n_models <= 1 or delta.dtas_std_c == 0:
        return ProjectedPotential(central, None, None, delta.dtas_c)
    lower = potential * index_factor(delta.dtas_c - delta.dtas_std_c, lo_r)
    upper = potential * index_factor(delta.dtas_c + delta.dtas_std_c, hi_r)
    return ProjectedPotential(central, min(lower, central), max(upper, central), delta.dtas_c)
