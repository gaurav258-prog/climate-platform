"""Frost-EXTENT severity — the interannually-discriminating frost hazard metric.

The per-cell frost score (ml/scoring/frost_climatology) answers "how cold at THIS plot". This module
answers the REGIONAL question "how much of the belt froze this winter" — the fraction of a region's
cells whose season-minimum 2m temperature fell to/below a crop-damaging threshold. That fraction is
what discriminates the catastrophic frost years (Brazil coffee: 1994, 2021, 2000) from a normal
winter; the region's single coldest cell saturates near the damage threshold almost every year and
carries no interannual signal, so it cannot be used as a severity index. See
scripts/analyze_coffee_frost_extent.py for the validation that established this.

Used as a regional frost-SEVERITY signal (a KRI / event indicator), NOT as a per-plot score and NOT
as a calibrated €: the frost→yield link does not clear the r²≥0.40 publish gate at any resolution,
so this reports HAZARD severity, never a euro.
"""
from __future__ import annotations

import h3

from ml.features.frost import to_h3_frame

# 2m screen-height ~2°C ≈ leaf-level 0°C frost damage for arabica (COFFEE_FROST_MILD in frost_climatology).
DAMAGE_THRESHOLD_C = 2.0
FROST_MONTHS = [5, 6, 7, 8, 9]          # austral winter (Southern-hemisphere frost season)

# Severity bands over the frozen-area fraction. Calibrated to the Brazil-coffee record (severe historical
# frosts 0.44–0.60; ordinary winters < 0.10). Bands, not a euro — the number is a hazard extent.
_BANDS = ((0.30, "severe"), (0.10, "elevated"), (0.0, "normal"))


def severity_band(extent: float | None) -> str:
    """Map a frozen-area fraction (0–1) to a severity band. None → 'unknown'."""
    if extent is None:
        return "unknown"
    for floor, name in _BANDS:
        if extent >= floor:
            return name
    return "normal"


def frost_extent(ds, year: int, bbox: tuple[float, float, float, float] | None = None,
                 thr: float = DAMAGE_THRESHOLD_C, months: list[int] | None = None) -> float | None:
    """Fraction of region cells whose season-minimum 2m temperature fell to/below `thr` in `year`.

    ds: an ERA5 frost-hourly dataset (ml.features.frost.load_hourly_years).
    bbox: optional (lat_min, lat_max, lon_min, lon_max) to restrict to a sub-region so a frost-free
          area doesn't dilute the signal (e.g. the frost-prone Sul-de-Minas coffee heartland).
    Returns None when the year has no data in the region.
    """
    df = to_h3_frame(ds, year, months or FROST_MONTHS)
    if df.empty:
        return None
    if bbox:
        la = df["h3_cell"].map(lambda c: h3.cell_to_latlng(c)[0])
        lo = df["h3_cell"].map(lambda c: h3.cell_to_latlng(c)[1])
        df = df[(la >= bbox[0]) & (la <= bbox[1]) & (lo >= bbox[2]) & (lo <= bbox[3])]
    if len(df) == 0:
        return None
    return round(float((df["season_min_tmin_c"] <= thr).mean()), 4)
