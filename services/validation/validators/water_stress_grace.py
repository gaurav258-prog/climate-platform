"""Water-stress validator — the chronic root-zone aridity channel (hazard_type 'soil_water') against what the
GRACE / GRACE-FO gravimetry satellites observed of terrestrial water storage, on the ledger.

Why this is the honest target: the channel is a pure function of the ERA5 root-zone soil-moisture baseline
(ml/scoring/water_stress_point.py). GRACE measures the total column of water (soil + groundwater + surface
water + snow/ice) from its gravity signal — a physically independent observation. The observed quantity is the
per-cell OLS trend of monthly liquid-water-equivalent thickness 2002-04 → 2026-03 (NASA GSFC RL06 v2.0 mascons,
GIA removed with ICE6G-D; scripts/fetch_grace_trends.py), expressed as a DECLINE rate (cm/yr, declining positive)
so a higher observed value means water is being lost faster. One `rank` test (Spearman ≥ 0.35 + monotone bands):
does the chronic-aridity score order the world's land the way the observed storage-loss rate does?

Cells dominated by ice mass loss or by residual glacial-isostatic rebound are excluded by DECLARED bounding
rules (EXCLUSION_BOXES below): Antarctica, Greenland, Iceland, Svalbard and the high Arctic, Alaska/Yukon
coastal icefields, Patagonian icefields, the Tibetan Plateau / Karakoram / Tien Shan glacier belt, Fennoscandia
and the Hudson Bay / Laurentide rebound region. Everything else on land is in.

Predicted = the platform's soil_water score at the H3 res-8 cell of the GRACE cell centre. The channel holds a
GLOBAL baseline but is scored on demand, so cells without a standing score are scored with the point scorer
(count reported in the run notes); a cell where the baseline has no coverage is absent, never filled. The GRACE
lattice is sampled at STEP_DEG (default 2°) to keep the on-demand scoring tractable — declared in the notes.
Needs data/water_stress_val/grace_gsfc_trends.csv; absent → INSUFFICIENT.
"""
from __future__ import annotations

import os
from pathlib import Path

import h3
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.validation.engine import ValidationResult, register

TRENDS_CSV = Path("data/water_stress_val/grace_gsfc_trends.csv")
STEP_DEG = float(os.environ.get("WATER_STRESS_GRACE_STEP", "2"))
SOURCE_URL = "https://earth.gsfc.nasa.gov/geo/data/grace-mascons"
TARGET = "NASA GSFC GRACE/GRACE-FO RL06 v2.0 mascons — observed terrestrial water-storage decline rate 2002–2026 (cm/yr)"

# (name, lat_min, lat_max, lon_min, lon_max) — a cell whose centre falls inside any box is excluded.
EXCLUSION_BOXES: tuple[tuple[str, float, float, float, float], ...] = (
    ("antarctica", -90.0, -60.0, -180.0, 180.0),
    ("greenland", 59.0, 84.0, -75.0, -10.0),
    ("iceland", 63.0, 67.0, -25.0, -13.0),
    ("high_arctic_svalbard_canadian_archipelago", 72.0, 90.0, -180.0, 180.0),
    ("alaska_yukon_icefields", 55.0, 65.0, -150.0, -125.0),
    ("patagonian_icefields", -55.0, -40.0, -76.0, -68.0),
    ("tibetan_plateau", 30.0, 40.0, 78.0, 100.0),          # plateau/Himalaya glacier belt, Indo-Gangetic plain stays IN
    ("karakoram_west_himalaya", 32.0, 40.0, 74.0, 78.0),
    ("tien_shan_pamir", 36.0, 45.0, 68.0, 85.0),
    ("fennoscandia_gia", 55.0, 72.0, 5.0, 35.0),
    ("hudson_bay_laurentide_gia", 48.0, 72.0, -100.0, -60.0),
)


def excluded_by(lat: float, lon: float) -> str | None:
    """Name of the first declared exclusion box containing the point, or None."""
    for name, la0, la1, lo0, lo1 in EXCLUSION_BOXES:
        if la0 <= lat <= la1 and lo0 <= lon <= lo1:
            return name
    return None


def on_lattice(lat: float, lon: float, step_deg: float = STEP_DEG, src_deg: float = 1.0) -> bool:
    """Keep every (step/src)-th node of the source lattice in each axis (cell centres sit at x.25/x.75)."""
    k = max(1, int(round(step_deg / src_deg)))
    i = int(round((lat + 89.75) / src_deg))
    j = int(round((lon + 179.75) / src_deg))
    return i % k == 0 and j % k == 0


def decline_rate(trend_cm_yr: float) -> float:
    """Storage LOSS is the hazard: flip the sign so declining storage is positive."""
    return -float(trend_cm_yr)


def select_cells(rows: list[dict], step_deg: float = STEP_DEG) -> tuple[list[dict], dict[str, int]]:
    """Apply the lattice sampling and the declared exclusions; returns (kept rows, exclusion counts)."""
    kept, counts = [], {}
    for r in rows:
        lat, lon = float(r["lat"]), float(r["lon"])
        if not on_lattice(lat, lon, step_deg):
            continue
        why = excluded_by(lat, lon)
        if why:
            counts[why] = counts.get(why, 0) + 1
            continue
        kept.append({"lat": lat, "lon": lon, "obs": decline_rate(r["trend_cm_yr"]), "n_months": int(r["n_months"]),
                     "h3_cell": h3.latlng_to_cell(lat, lon, 8)})
    return kept, counts


def _standing_scores(session: Session, cells: list[str]) -> dict[str, float]:
    if not cells:
        return {}
    rows = session.execute(text("""
        SELECT h3_cell, CAST(risk_score AS FLOAT) AS rs FROM canonical_scores
        WHERE hazard_type = 'soil_water' AND scenario = 'baseline' AND time_horizon = 'current' AND valid_to IS NULL
          AND h3_cell = ANY(:cells)
    """), {"cells": cells}).all()
    return {c: float(rs) for c, rs in rows}


def _grace(session: Session) -> ValidationResult:
    if not TRENDS_CSV.exists():
        return ValidationResult(hazard_type="soil_water", kind="rank", predicted=[], observed=[], labels=[],
                                target_source=TARGET, scope="global", method="out_of_sample",
                                notes=f"target file {TRENDS_CSV} not present — run scripts/fetch_grace_trends.py")
    import pandas as pd

    from ml.scoring.water_stress_point import score_water_stress_point
    raw = pd.read_csv(TRENDS_CSV).to_dict("records")
    cells, excl = select_cells(raw, STEP_DEG)
    have = _standing_scores(session, [c["h3_cell"] for c in cells])
    n_scored = n_nodata = 0
    for c in cells:
        if c["h3_cell"] in have:
            continue
        r = score_water_stress_point(c["lat"], c["lon"])
        if r.get("status") == "insufficient_data":
            n_nodata += 1
            continue
        n_scored += 1
        have[c["h3_cell"]] = float(r["risk_score"])
    pred, obs, labels = [], [], []
    for c in cells:
        if c["h3_cell"] not in have:
            continue
        pred.append(have[c["h3_cell"]]); obs.append(c["obs"]); labels.append(f"{c['lat']:.2f},{c['lon']:.2f}")
    excl_txt = ", ".join(f"{k}={v}" for k, v in sorted(excl.items())) or "none"
    return ValidationResult(
        hazard_type="soil_water", kind="rank", predicted=pred, observed=obs, labels=labels,
        target_source=TARGET, scope="global", method="out_of_sample",
        data_vintage="GSFC RL06v2 mascons 2002-04→2026-03, GIA-removed ICE6G-D",   # ≤60 chars (ledger column)
        notes=(f"channel score at the H3 res-8 cell of each GRACE 1° land cell centre (lattice sampled at {STEP_DEG:g}°) vs the "
               f"independently observed GRACE storage-decline rate ({SOURCE_URL}); {len(have) - n_scored} cells had a standing score, "
               f"{n_scored} scored on demand, {n_nodata} without baseline coverage (absent, never filled); "
               f"declared exclusions (ice/GIA): {excl_txt}. Caveat: GRACE trends mix groundwater pumping, drought "
               f"cycles, reservoir filling and snow — a total-storage target, not a soil-moisture one."),
    )


register("water_stress_grace")(_grace)
