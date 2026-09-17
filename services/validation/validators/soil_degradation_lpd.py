"""Soil-degradation validator — the platform's channel (hazard_type 'soil_degradation', reading Trends.Earth
SDG 15.3.1 degraded-land status) against the independent Li et al. (2025) 30 m Land Productivity Dynamics
(LPD) dataset, on the ledger.

Why this is an independent target: our channel reads the Trends.Earth SDG 15.3.1 product (Conservation
International; Zenodo 10.5281/zenodo.17079487) — ESA-CCI land cover + productivity dynamics + SoilGrids soil
organic carbon, per the UNCCD Good Practice Guidance. Li et al. 2025 ("A 30-meter resolution global land
productivity dynamics dataset from 2013 to 2022", Zenodo 10.5281/zenodo.14512248) is a genuinely different
product: Landsat-8 + MODIS imagery run through the FAO-WOCAT LPD methodology, a different pipeline and a
different institution, sharing only the general concept (productivity trend as a land-degradation proxy).

Target: data/degradation_val/li_lpd_sample.csv (scripts/build_lpd_degradation_sample.py) — a ~4,000-point
grid sample (0.1° lattice, randomly subsampled to a fixed size) of the two downloaded Mediterranean-basin LPD
tiles (Iberia+France and Italy/Greece/Balkans/Levant, lon -45..45, lat 28..52N), restricted to on-legend
pixels (1-5; 0 = no data, dropped). Absent → INSUFFICIENT, never fabricated.

Polarity: the source legend is ORDINAL health, not severity — 1 = declining LPD, 2 = early signs of decline,
3 = stable but stressed, 4 = stable and not stressed, 5 = increasing LPD (higher = healthier land). Our
channel's score runs the other way (higher = more degraded), so the observed value is flipped to
DEGRADATION SEVERITY = 6 - lpd_status (1→5 declining/worst, 5→1 improving/best) before the rank test, so a
positive Spearman correlation means "our score is high where Li et al. observed the land declining."

Predicted = the platform's soil_degradation score at the H3 res-8 cell of each sample point. A cell without a
standing score is scored on demand with the point scorer (services/geo/raster_sampler already picks up the
locally-materialised Trends.Earth raster at data/soil_degradation/degradation.tif when present, so this run
never needs the remote COG); the count scored on demand vs pre-existing is written to the run notes.
"""
from __future__ import annotations

from pathlib import Path

import h3
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.validation.engine import ValidationResult, register

TARGET_CSV = Path("data/degradation_val/li_lpd_sample.csv")
TARGET = "Li et al. 2025 30m Land Productivity Dynamics, Mediterranean tiles (Zenodo 14512248, Landsat-8+MODIS/FAO-WOCAT)"
H3_RES = 8


def degradation_severity(lpd_status: int) -> float:
    """Flip the source's health-ordinal (1=declining..5=increasing) to a severity scale so higher = worse,
    matching our channel's polarity (higher score = more degraded)."""
    return 6.0 - float(lpd_status)


def _aggregate(rows: list[dict]) -> dict[str, dict]:
    """Per-res-8-cell mean observed severity from sample rows {lat, lon, lpd_status}."""
    acc: dict[str, dict] = {}
    for r in rows:
        lat, lon = float(r["lat"]), float(r["lon"])
        cell = h3.latlng_to_cell(lat, lon, H3_RES)
        a = acc.setdefault(cell, {"sum": 0.0, "n": 0, "lat": lat, "lon": lon})
        a["sum"] += degradation_severity(int(r["lpd_status"]))
        a["n"] += 1
    return {c: {"obs": a["sum"] / a["n"], "n": a["n"], "lat": a["lat"], "lon": a["lon"]} for c, a in acc.items()}


def _existing_scores(session: Session, cells: list[str]) -> dict[str, float]:
    if not cells:
        return {}
    rows = session.execute(text("""
        SELECT h3_cell, CAST(risk_score AS FLOAT) rs FROM canonical_scores
        WHERE hazard_type='soil_degradation' AND scenario='baseline' AND time_horizon='current' AND valid_to IS NULL
          AND h3_cell = ANY(:cells)
    """), {"cells": cells}).all()
    return {c: float(s) for c, s in rows}


def _run(session: Session) -> ValidationResult:
    if not TARGET_CSV.exists():
        return ValidationResult(hazard_type="soil_degradation", kind="rank", predicted=[], observed=[], labels=[],
                                target_source=TARGET, scope="mediterranean", method="out_of_sample",
                                notes=f"target file {TARGET_CSV} not present — run scripts/build_lpd_degradation_sample.py")
    import csv

    from ml.scoring.soil_degradation_point import score_soil_degradation_point

    with open(TARGET_CSV, newline="") as f:
        raw = list(csv.DictReader(f))
    cells = _aggregate(raw)
    ids = sorted(cells)
    scores = _existing_scores(session, ids)
    n_pre = len(scores)
    n_demand = n_nodata = 0
    for c in ids:
        if c in scores:
            continue
        r = score_soil_degradation_point(cells[c]["lat"], cells[c]["lon"])
        if r.get("status") in ("scored", "cached_hit") and r.get("risk_score") is not None:
            scores[c] = float(r["risk_score"]); n_demand += 1
        else:
            n_nodata += 1   # no Trends.Earth coverage at this cell — absent, never filled

    pred, obs, labels = [], [], []
    for c in ids:
        if c not in scores:
            continue
        pred.append(scores[c]); obs.append(cells[c]["obs"]); labels.append(f"{c} n={cells[c]['n']}")

    return ValidationResult(
        hazard_type="soil_degradation", kind="rank", predicted=pred, observed=obs, labels=labels,
        target_source=TARGET, scope="mediterranean", method="out_of_sample",
        data_vintage="Li LPD 2013-2022 vs Trends.Earth SDG 15.3.1 2000-2023"[:60],
        notes=(f"platform soil_degradation score at the res-8 cell of each Li et al. LPD grid-sample point "
               f"(0.1° lattice over the two downloaded Mediterranean tiles, lon -45..45 / lat 28..52N) vs the "
               f"observed degradation severity (6 - lpd_status, so higher = worse, matching our score's polarity); "
               f"{len(pred)} cells from {len(raw)} sample points; {n_pre} cells had a platform score already, "
               f"{n_demand} scored on demand via the point scorer (reads the locally-materialised Trends.Earth "
               f"raster at data/soil_degradation/degradation.tif), {n_nodata} had no Trends.Earth coverage and are "
               f"absent. Different institution, different imagery pipeline (Landsat-8+MODIS/FAO-WOCAT vs ESA-CCI/"
               f"SoilGrids/Conservation International) from our model's source — a genuinely independent target, "
               f"restricted to the Mediterranean basin (the only region with downloaded LPD tiles)."),
    )


register("soil_degradation_lpd")(_run)
