"""Permafrost validator — the thaw-exposure channel (ml/scoring/permafrost_point.py, Obu et al. 2019 TTOP
Permafrost Probability Fraction raster) against ground temperature the GTN-P (Global Terrestrial Network for
Permafrost) boreholes actually measured.

Why this is the honest target: the channel is a pure function of the Obu (2019) probability raster
(data/permafrost/PERPROB.tif). GTN-P boreholes independently measure ground temperature with in-situ
thermistor strings — a physically independent observation, never an input to the raster's own TTOP model run
we read. The observed quantity is Mean Annual Ground Temperature (MAGT) at the depth closest to the
zero-annual-amplitude zone (target 10 m, GTN-P's own convention for judging permafrost presence/condition —
see scripts/build_permafrost_boreholes.py), inverted to a COLDNESS statistic (-MAGT, degC) so a higher observed
value means colder, more stable permafrost. One `rank` test (Spearman >= 0.35 + monotone bands): does the
raster-derived probability score order these 239 European/Arctic sites the way their own measured ground
temperature does? A borehole with MAGT near or above 0 degC has thawed or degrading permafrost and should sit
at a LOW observed value (low coldness); the platform's score is expected to run low there too.

Predicted = the platform's permafrost score (0-100) at the H3 res-8 cell of each borehole, read from
canonical_scores when already scored, otherwise scored on demand with the point scorer (counted). Sites off the
raster's NH >=25N domain, on nodata pixels (e.g. glaciated summit pixels — observed at Kitzsteinhorn AT), or with
no reachable score are dropped, never filled.

Data: data/permafrost_val/borehole_magt.csv (built by scripts/build_permafrost_boreholes.py from the raw GTN-P
export data/permafrost_val/permafrost_ground_temp_europe.csv, 4.9M rows, 389 boreholes, via
data/permafrost_val/boreholes_europe_meta.json for coordinates). Absent -> INSUFFICIENT.

Caveats (declared, not hidden): MAGT here is a plain mean of all qualifying daily readings at the chosen depth,
not a true annual-cycle fit, so it is noisier at sites with short or gappy records. The chosen depth is the
closest available to 10 m with >=300 qualifying daily readings spanning >=1 calendar year; many GTN-P sites
only log shallow instruments (some boreholes' best available depth is under 1 m), where MAGT still carries
residual seasonal signal rather than the fully damped deep-ground value — reported per-row via `depth_m` in the
CSV, not filtered out, since excluding them would bias the sample toward the best-instrumented sites. Borehole
coverage skews toward Fennoscandia, the Alps and Western Siberia; it is not a uniform sample of the NH
permafrost domain.
"""
from __future__ import annotations

import csv
from pathlib import Path

import h3
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.validation.engine import ValidationResult, register

MAGT_CSV = Path("data/permafrost_val/borehole_magt.csv")
TARGET = "GTN-P borehole mean annual ground temperature (MAGT) at ~10 m depth, 239 European/Arctic sites (data.gtn-p.org)"
SOURCE_URL = "https://data.gtn-p.org/"


def _coldness(magt_c: float) -> float:
    """Observed severity = coldness: colder ground (more negative MAGT) -> higher value."""
    return -float(magt_c)


def load_boreholes(csv_path: Path = MAGT_CSV) -> list[dict]:
    if not csv_path.exists():
        return []
    rows = []
    with csv_path.open() as f:
        for r in csv.DictReader(f):
            rows.append({
                "borehole_id": int(r["borehole_id"]), "lat": float(r["lat"]), "lon": float(r["lon"]),
                "country": r.get("country") or "", "depth_m": float(r["depth_m"]),
                "magt_c": float(r["magt_c"]), "n_obs": int(r["n_obs"]), "n_years": int(r["n_years"]),
                "h3_cell": h3.latlng_to_cell(float(r["lat"]), float(r["lon"]), 8),
            })
    return rows


def _standing_scores(session: Session, cells: list[str]) -> dict[str, float]:
    if not cells:
        return {}
    rows = session.execute(text("""
        SELECT h3_cell, CAST(risk_score AS FLOAT) AS rs FROM canonical_scores
        WHERE hazard_type = 'permafrost' AND scenario = 'baseline' AND time_horizon = 'current' AND valid_to IS NULL
          AND h3_cell = ANY(:cells)
    """), {"cells": cells}).all()
    return {c: float(rs) for c, rs in rows}


def _run(session: Session) -> ValidationResult:
    if not MAGT_CSV.exists():
        return ValidationResult(hazard_type="permafrost", kind="rank", predicted=[], observed=[], labels=[],
                                target_source=TARGET, scope="Europe/Arctic", method="out_of_sample",
                                notes=f"target file {MAGT_CSV} not present — run scripts/build_permafrost_boreholes")
    from ml.scoring.permafrost_point import score_permafrost_point

    boreholes = load_boreholes()
    have = _standing_scores(session, [b["h3_cell"] for b in boreholes])
    n_scored = n_nodata = 0
    for b in boreholes:
        if b["h3_cell"] in have:
            continue
        r = score_permafrost_point(b["lat"], b["lon"])
        if r.get("status") == "insufficient_data":
            n_nodata += 1
            continue
        n_scored += 1
        have[b["h3_cell"]] = float(r["risk_score"])

    pred, obs, labels = [], [], []
    for b in boreholes:
        if b["h3_cell"] not in have:
            continue
        pred.append(have[b["h3_cell"]]); obs.append(_coldness(b["magt_c"]))
        labels.append(f"gtnp_{b['borehole_id']}_{b['country']}")

    shallow = sum(1 for b in boreholes if b["h3_cell"] in have and b["depth_m"] < 3.0)
    return ValidationResult(
        hazard_type="permafrost", kind="rank", predicted=pred, observed=obs, labels=labels,
        target_source=TARGET, scope="Europe/Arctic", method="out_of_sample",
        data_vintage="GTN-P daily ground temp, 1891-2026 (per-site, varies)",  # <=60 chars
        notes=(f"permafrost score at the H3 res-8 cell of each of {len(boreholes)} GTN-P boreholes vs "
               f"independently measured coldness (-MAGT) at the depth nearest 10 m ({SOURCE_URL}); "
               f"{len(have) - n_scored} cells had a standing score, {n_scored} scored on demand, {n_nodata} "
               f"off the raster's NH>=25N domain or on a nodata pixel (dropped, never filled); {shallow} used "
               f"sites had their best qualifying depth under 3 m (shallower instrument, residual seasonal "
               f"signal, not excluded — see docstring). Caveat: MAGT is a plain mean of daily readings, not an "
               f"annual-cycle fit; coverage skews to Fennoscandia/Alps/W. Siberia, not a uniform NH sample."),
    )


register("permafrost_gtnp")(_run)
