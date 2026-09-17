"""Soil-erosion validator — the GloSEM point channel (ml/scoring/soil_erosion_point.py, hazard_type
'soil_erosion') against catchment-observed suspended-sediment yield from the EUSEDcollab network.

Why this is the honest target: GloSEM (Borrelli/Panagos) is a RUSLE-family MODEL of gross hillslope soil
displacement by water erosion, not a direct measurement. EUSEDcollab (github.com/eusedcollab, EGU data
descriptor Vanmaercke et al.) is a network of 251 small European catchments with gauged discharge (Q) and
suspended-sediment load (SSL) time series — genuinely OBSERVED, independent of GloSEM's RUSLE inputs
(rainfall erosivity, soil erodibility, LS-factor, cover-management, support practice). The observed quantity
is each catchment's specific sediment yield (SSY, t ha⁻¹ yr⁻¹): total measured SSL over the catchment's full
record, divided by its drainage area and by the record's real span in years — the same units GloSEM reports
in, so no scale conversion is needed for the rank test.

Two disclosed simplifications:
  1. Point vs areal — GloSEM is sampled at the catchment's reported station (lat, lon), a point, not an areal
     mean over the catchment polygon (EUSEDcollab ships no catchment boundaries). For catchments at ~10-1000
     ha this point sample sits inside or very near the contributing area; acceptable, same posture as
     flood_jrc.py / coastal_gauges.py sampling at a station point rather than routing a full field.
  2. Gross erosion vs net yield — GloSEM estimates gross hillslope displacement; SSY at a catchment outlet is
     a NET yield after in-catchment sediment redeposition (the sediment delivery ratio, which shrinks with
     catchment area and is not modelled here). The two are expected to correlate in RANK, not in absolute
     magnitude, which is exactly what this test checks (kind='rank', Spearman).

Prep: scripts/ingest_erosion_eusedcollab.py turns the raw Q_SSL/*.csv files + ALL_METADATA.csv into
data/erosion_val/eusedcollab_ssy.csv (catchment_id, lat, lon, ssy_t_ha_yr, years, n_records, data_type,
drainage_ha). Catchments whose only sediment record is a rating-curve estimate (no measured SSL column) are
excluded in that prep step — a regression estimate is not an independent observation. Needs that CSV; absent
→ INSUFFICIENT.

SDR-adjusted extra: the CSV also carries each catchment's drainage_ha (present for all rows), so this
validator additionally reports (in `extra`, alongside the unadjusted headline metric) the rank correlation
after scaling GloSEM's gross rate by the Boyce (1975) sediment-delivery-ratio curve
(ml/scoring/soil_erosion_sdr.py) — SDR(A) = 0.5656 * A_km2^-0.11, a cited curve, not fitted to this data —
before comparing to observed SSY. Both numbers are kept: the unadjusted one is the headline/ledger metric
(gross point-scale skill), the SDR-adjusted one (extra["sdr_spearman"]) tests the delivery-corrected claim.
"""
from __future__ import annotations

from pathlib import Path

import h3
from sqlalchemy import text
from sqlalchemy.orm import Session

from ml.validation import metrics as M
from services.validation.engine import ValidationResult, register

SSY_CSV = Path("data/erosion_val/eusedcollab_ssy.csv")
TARGET = "EUSEDcollab catchment network — observed specific sediment yield (SSY, t ha⁻¹ yr⁻¹) from gauged Q/SSL records"
SOURCE_NOTE = "Vanmaercke et al., EUSEDcollab (github.com/eusedcollab); data/erosion_val/eusedcollab/"


def _standing_scores(session: Session, cells: list[str]) -> dict[str, float]:
    if not cells:
        return {}
    rows = session.execute(text("""
        SELECT h3_cell, CAST(risk_score AS FLOAT) AS rs FROM canonical_scores
        WHERE hazard_type = 'soil_erosion' AND scenario = 'baseline' AND time_horizon = 'current' AND valid_to IS NULL
          AND h3_cell = ANY(:cells)
    """), {"cells": cells}).all()
    return {c: float(rs) for c, rs in rows}


def _run(session: Session) -> ValidationResult:
    if not SSY_CSV.exists():
        return ValidationResult(hazard_type="soil_erosion", kind="rank", predicted=[], observed=[], labels=[],
                                target_source=TARGET, scope="Europe (EUSEDcollab catchments)", method="out_of_sample",
                                notes=f"prepped target file {SSY_CSV} not present — run "
                                      f"python -m scripts.ingest_erosion_eusedcollab")
    import csv

    from ml.scoring.soil_erosion_point import score_soil_erosion_point
    rows = list(csv.DictReader(SSY_CSV.open()))
    catchments = []
    for r in rows:
        try:
            lat, lon, ssy = float(r["lat"]), float(r["lon"]), float(r["ssy_t_ha_yr"])
        except (TypeError, ValueError):
            continue
        try:
            drainage_km2 = float(r["drainage_ha"]) / 100.0
        except (TypeError, ValueError, KeyError):
            drainage_km2 = None
        catchments.append({"lat": lat, "lon": lon, "ssy": ssy, "id": r["catchment_id"], "name": r["name"],
                           "country": r["country"], "h3_cell": h3.latlng_to_cell(lat, lon, 8),
                           "drainage_km2": drainage_km2})

    have = _standing_scores(session, [c["h3_cell"] for c in catchments])
    n_scored = n_nodata = 0
    for c in catchments:
        if c["h3_cell"] in have:
            continue
        res = score_soil_erosion_point(c["lat"], c["lon"])
        if res.get("status") == "insufficient_data":
            n_nodata += 1
            continue
        n_scored += 1
        have[c["h3_cell"]] = float(res["risk_score"])

    pred, obs, labels, areas = [], [], [], []
    for c in catchments:
        if c["h3_cell"] not in have:
            continue
        pred.append(have[c["h3_cell"]]); obs.append(c["ssy"])
        labels.append(f"{c['id']}:{c['name']} ({c['country']})")
        areas.append(c["drainage_km2"])

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
        target_source=TARGET, scope="Europe (EUSEDcollab catchments)", method="out_of_sample",
        data_vintage="EUSEDcollab repo, 251 catchments, through 2021-24",   # ≤60 chars
        extra=extra,
        notes=(f"channel score at the point of each EUSEDcollab gauging station ({len(catchments)} catchments "
               f"with a usable SSY, {len(have) - n_scored} had a standing score, {n_scored} scored on demand, "
               f"{n_nodata} outside GloSEM raster coverage — absent, never filled) vs observed specific sediment "
               f"yield from the gauged Q/SSL record ({SOURCE_NOTE}). Point-sampled at the station, not catchment-"
               f"areal-averaged (no catchment polygons shipped); gross RUSLE displacement vs net catchment-outlet "
               f"yield — headline metric is unadjusted (rank test only, not a magnitude match); extra.sdr_spearman "
               f"applies the Boyce (1975) area-dependent sediment-delivery-ratio (ml/scoring/soil_erosion_sdr.py) "
               f"to the gross rate before ranking against observed SSY, using each catchment's drainage_ha. Sample "
               f"skews heavily Danish (small agricultural catchments dominate EUSEDcollab); disclosed, not "
               f"reweighted."),
    )


def _r(v):
    return round(v, 4) if isinstance(v, float) else v


register("soil_erosion_eusedcollab")(_run)
