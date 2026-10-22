"""Global-warming level (GWL) — the physical time axis forward projections interpolate ALONG, read from the platform's
one timeline (services.reference.warming_axis; the product owner's decisions of 2026-10-22).

Warming is non-linear in time and the hazard response is (to first order) linear in warming, so a year between two of
the engine's modelled horizons is the blend of the two weighted by its warming level, not by the calendar fraction:

    w = (GWL(year) − GWL(lower horizon)) / (GWL(upper horizon) − GWL(lower horizon))      clamped to [0, 1]

GWL(year) is the IPCC AR6 assessed 20-year level for that year under the pathway; a horizon's GWL is the level of what
it models — 'current' its year's level, 2030/2050/2100 their periods' (2021–2040, 2041–2060, 2081–2100). Earlier this
module read a curve built from the platform's four-model CMIP6 set with today's warming typed in (+0.30 °C, against
+0.39 °C in the HadCRUT5 record it cited — E316); that curve and its builder are gone.

A pathway with no warming (baseline) returns None → the caller blends by the calendar fraction, honest there.
"""
from __future__ import annotations

from typing import Optional

from services.reference import warming_axis as axis


def warming_level(scenario: str, year: int) -> Optional[float]:
    """The assessed 20-year level (°C above 1995–2014) of a year under a pathway, or None (no pathway, or outside the
    assessed series)."""
    v = axis.level(scenario, year) if axis.ssp(scenario) else None
    return None if v is None else v["central"]


def horizon_level(scenario: str, label: str) -> Optional[float]:
    """The level of a modelled horizon ('current', '2030', '2050', '2100') under a pathway."""
    v = axis.anchor(scenario, label) if axis.ssp(scenario) else None
    return None if v is None else v["central"]


def weight(scenario: str, lo_year: int, hi_year: int, target_year: int) -> Optional[float]:
    """Blend weight for `target_year` between the horizons at `lo_year` and `hi_year`, along the warming axis. None when
    the pathway carries no warming or the two horizons sit at the same level (the caller then uses the calendar)."""
    from services.intelligence.horizon import ANCHORS
    label = {yr: lbl for yr, lbl in ANCHORS}
    glo = horizon_level(scenario, label.get(lo_year, ""))
    ghi = horizon_level(scenario, label.get(hi_year, ""))
    gy = warming_level(scenario, target_year)
    if glo is None or ghi is None or gy is None or ghi == glo:
        return None
    return max(0.0, min(1.0, (gy - glo) / (ghi - glo)))


def available() -> bool:
    return True
