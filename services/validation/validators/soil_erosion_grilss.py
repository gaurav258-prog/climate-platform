"""Soil-erosion validator (second, complementary target) — the GloSEM point channel
(ml/scoring/soil_erosion_point.py, hazard_type 'soil_erosion') against observed reservoir sedimentation from
GRILSS, the Global Reservoir Inventory of Lost Storage by Sedimentation (1,368 reservoirs, 75 basins, 54
countries — global reach, unlike EUSEDcollab's Europe-only network).

Why this is a genuine, independent target: a reservoir's measured loss of storage capacity over its
operating life is the integrated erosion + sediment-transport + deposition outcome of its ENTIRE upstream
catchment — a real physical consequence, observed by bathymetric/hydrographic resurvey, not modelled from
the same RUSLE inputs GloSEM uses. The observed quantity here is a volumetric specific sedimentation rate:
`Sedimentation Rate (MCM/year)` × 1e6 m³/MCM ÷ (`Catchment Area (Km²)` × 100 ha/km²) = m³ ha⁻¹ yr⁻¹. GRILSS's
own mass field (`Sedimentation Amount (MT)`) is populated for only 33 of 1,368 rows, so the volumetric rate
(populated for all rows) is used instead; this is a Spearman RANK test, so the missing mass→volume bulk-
density conversion (typically 1.0-1.6 t/m³ for reservoir deposits) does not need to be applied or assumed —
only claimed, honestly, as a volumetric rather than mass proxy.

Filters applied (disclosed, not tuned to the result): GRILSS's own `GRAND Wrong Location` / `GDAT Wrong
Location` / `Dam Removed or Dried` / `Creek Dam` flags are excluded; a non-positive sedimentation rate or
catchment area is excluded (25 GRILSS rows record net *capacity gain*, e.g. flushed or re-dredged reservoirs
— not a soil-erosion signal). No fetch script: GRILSS ships as a single small xlsx already in
data/erosion_val/grilss/, read directly here. Needs that file; absent → INSUFFICIENT.

SDR-adjusted extra: GRILSS's own `Catchment Area (Km^2)` column (used for the volumetric proxy above, so
already 100% populated on the filtered rows) also lets this validator report (in `extra`, alongside the
unadjusted headline metric) the rank correlation after scaling GloSEM's gross rate by the Boyce (1975)
sediment-delivery-ratio curve (ml/scoring/soil_erosion_sdr.py) — SDR(A) = 0.5656 * A_km2^-0.11, a cited curve,
not fitted to this data — before comparing to the observed volumetric sedimentation rate. Both numbers are
kept: the unadjusted one is the headline/ledger metric, the SDR-adjusted one (extra["sdr_spearman"]) tests the
delivery-corrected claim.
"""
from __future__ import annotations

from pathlib import Path

import h3
from sqlalchemy import text
from sqlalchemy.orm import Session

from ml.validation import metrics as M
from services.validation.engine import ValidationResult, register

GRILSS_XLSX = Path("data/erosion_val/grilss/GRILSS_v1.2/Sedimentation_data/GRILSS_data_v1.2.xlsx")
TARGET = "GRILSS — Global Reservoir Inventory of Lost Storage by Sedimentation (observed volumetric sedimentation rate)"


def _standing_scores(session: Session, cells: list[str]) -> dict[str, float]:
    if not cells:
        return {}
    rows = session.execute(text("""
        SELECT h3_cell, CAST(risk_score AS FLOAT) AS rs FROM canonical_scores
        WHERE hazard_type = 'soil_erosion' AND scenario = 'baseline' AND time_horizon = 'current' AND valid_to IS NULL
          AND h3_cell = ANY(:cells)
    """), {"cells": cells}).all()
    return {c: float(rs) for c, rs in rows}


def load_reservoirs() -> list[dict]:
    """Filtered (lat, lon, volumetric SSY proxy m3/ha/yr) rows from the raw GRILSS xlsx."""
    import pandas as pd
    df = pd.read_excel(GRILSS_XLSX)
    mask = (
        (df["GRAND Wrong Location"] == 0) & (df["GDAT Wrong Location"] == 0)
        & (df["Dam Removed or Dried"] == 0) & (df["Creek Dam"] == 0)
        & (df["Sedimentation Rate (MCM/year)"] > 0) & (df["Catchment Area (Km^2)"] > 0)
    )
    sub = df[mask].copy()
    sub["ssy_proxy_m3_ha_yr"] = sub["Sedimentation Rate (MCM/year)"] * 1e6 / (sub["Catchment Area (Km^2)"] * 100.0)
    out = []
    for _, r in sub.iterrows():
        out.append({"lat": float(r["Latitude"]), "lon": float(r["Longitude"]),
                    "ssy": float(r["ssy_proxy_m3_ha_yr"]), "name": str(r["Reservoir"]), "country": str(r["Country"]),
                    "area_km2": float(r["Catchment Area (Km^2)"])})
    return out


def _run(session: Session) -> ValidationResult:
    if not GRILSS_XLSX.exists():
        return ValidationResult(hazard_type="soil_erosion", kind="rank", predicted=[], observed=[], labels=[],
                                target_source=TARGET, scope="global", method="out_of_sample",
                                notes=f"target file {GRILSS_XLSX} not present")
    from ml.scoring.soil_erosion_point import score_soil_erosion_point
    reservoirs = load_reservoirs()
    for r in reservoirs:
        r["h3_cell"] = h3.latlng_to_cell(r["lat"], r["lon"], 8)

    have = _standing_scores(session, [r["h3_cell"] for r in reservoirs])
    n_scored = n_nodata = 0
    for r in reservoirs:
        if r["h3_cell"] in have:
            continue
        res = score_soil_erosion_point(r["lat"], r["lon"])
        if res.get("status") == "insufficient_data":
            n_nodata += 1
            continue
        n_scored += 1
        have[r["h3_cell"]] = float(res["risk_score"])

    pred, obs, labels, areas = [], [], [], []
    for r in reservoirs:
        if r["h3_cell"] not in have:
            continue
        pred.append(have[r["h3_cell"]]); obs.append(r["ssy"]); labels.append(f"{r['name']} ({r['country']})")
        areas.append(r["area_km2"])

    from ml.scoring.soil_erosion_point import rate_from_score
    from ml.scoring.soil_erosion_sdr import SDR_SOURCE, sediment_delivery_ratio
    n_area = sum(1 for a in areas if a)
    sdr_pred = [rate_from_score(p) * sediment_delivery_ratio(a) if a else None for p, a in zip(pred, areas)]
    sdr_pairs = [(p, o) for p, o in zip(sdr_pred, obs) if p is not None]
    extra = {
        "sdr_n": len(sdr_pairs), "sdr_n_with_area": n_area, "sdr_source": SDR_SOURCE,
        "sdr_spearman": _r(M.spearman([p for p, _ in sdr_pairs], [o for _, o in sdr_pairs])) if sdr_pairs else None,
    }

    return ValidationResult(
        hazard_type="soil_erosion", kind="rank", predicted=pred, observed=obs, labels=labels,
        target_source=TARGET, scope="global", method="out_of_sample",
        data_vintage="GRILSS v1.2, observed durations 1-296 yrs",   # ≤60 chars
        extra=extra,
        notes=(f"channel score at each reservoir's point (of {len(reservoirs)} filtered candidates: valid location, "
               f"not removed/dried, not a creek dam, positive rate and catchment area) — {len(have) - n_scored} had "
               f"a standing score, {n_scored} scored on demand, {n_nodata} outside GloSEM raster coverage (absent, "
               f"never filled) — vs observed volumetric sedimentation rate per catchment hectare (Sedimentation Rate "
               f"MCM/yr ÷ Catchment Area). Headline metric is unadjusted: catchment-integrated NET yield vs GloSEM's "
               f"point gross-displacement estimate, a rank test only. extra.sdr_spearman applies the Boyce (1975) "
               f"area-dependent sediment-delivery-ratio (ml/scoring/soil_erosion_sdr.py) to the gross rate using "
               f"GRILSS's own Catchment Area column before ranking. Volumetric, not mass (GRILSS's own mass field "
               f"covers only 33 of 1,368 reservoirs); no bulk-density conversion applied either way."),
    )


def _r(v):
    return round(v, 4) if isinstance(v, float) else v


register("soil_erosion_grilss")(_run)
