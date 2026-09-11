"""Coastal-erosion validator — the platform's projected-retreat score against satellite-OBSERVED historical
shoreline change (Luijendijk et al. 2018 Landsat product, 1984–2016), on the ledger.

  coastal_erosion_shoreline   kind 'rank'. Predicted = the platform's coastal_erosion score at the transect's
                              H3 res-8 cell; observed = the observed shoreline change rate (m/yr) with EROSION
                              POSITIVE, averaged over the transects in that cell. Gate: Spearman ≥ 0.35 + monotone
                              severity bands — the platform's standard for a ranking channel.

Target: data/coastal_erosion_val/wh_transects_shorelines_linearity.csv (scripts/fetch_shoreline_change.py;
Zenodo 3751980, CC-BY-4.0, Mentaschi et al. 2020) — per-transect linear-trend rate `coeflm` of the Luijendijk
2018 shoreline product in 67 coastal World Heritage Sites (the openly downloadable slice; the global product
sits behind a Deltares viewer / SAS-token store). Absent → INSUFFICIENT, never fabricated.

Two honesty points a reader must know:
  • The channel is defined ONLY under a projection scenario × horizon (baseline/current is 'insufficient_data'
    by design), so the score under test is the nearest-term projection (RCP4.5-mapped scenario, 2050; env
    COASTAL_EROSION_VAL_SCENARIO / _HORIZON). It is the number a customer sees, tested against what the coast
    actually did 1984–2016.
  • The platform scores very few coastal cells until assets sit on them, so transect cells without a score are
    scored on demand through the point scorer (the real product path); the count is written to the ledger.
    The projection's "ambient change" term was itself derived from the Luijendijk 2018 trends, so this backtest
    checks that the delivered score preserves the observed ranking — it is not a fully independent lineage.
"""
from __future__ import annotations

import os
from pathlib import Path

import h3
from sqlalchemy import text
from sqlalchemy.orm import Session

from ml.validation import metrics as M
from services.validation.engine import ValidationResult, register

TARGET_CSV = Path("data/coastal_erosion_val/wh_transects_shorelines_linearity.csv")
TARGET = "Luijendijk et al. 2018 Landsat shoreline change 1984–2016, World Heritage transects (Zenodo 3751980, CC-BY-4.0)"
SCENARIO = os.environ.get("COASTAL_EROSION_VAL_SCENARIO", "orderly_1_5c")
HORIZON = os.environ.get("COASTAL_EROSION_VAL_HORIZON", "2050")
MIN_SHORELINES = 17          # every transect in the file has ≥ 17 annual shorelines; guards a future re-pull
H3_RES = 8


def erosion_positive(rate_m_per_yr: float) -> float:
    """The file's trend is positive = accretion (seaward); the hazard is retreat, so flip the sign."""
    return -float(rate_m_per_yr)


def aggregate_transects(rows, min_shorelines: int = MIN_SHORELINES) -> dict:
    """Per-res-8-cell observed erosion (mean m/yr, erosion positive) from transect rows
    {lat, lon, rate, n_shorelines, linearity}. Returns {cell: {obs, n, obs_strong}} — obs_strong is the same mean
    over the file's own 'StrongLin' reliability subset (None when the cell has none)."""
    acc: dict = {}
    for r in rows:
        if r["n_shorelines"] < min_shorelines or r["rate"] is None or r["rate"] != r["rate"]:
            continue
        cell = h3.latlng_to_cell(float(r["lat"]), float(r["lon"]), H3_RES)
        a = acc.setdefault(cell, {"sum": 0.0, "n": 0, "sum_s": 0.0, "n_s": 0})
        e = erosion_positive(r["rate"])
        a["sum"] += e; a["n"] += 1
        if r.get("linearity") == "StrongLin":
            a["sum_s"] += e; a["n_s"] += 1
    return {c: {"obs": a["sum"] / a["n"], "n": a["n"],
                "obs_strong": (a["sum_s"] / a["n_s"]) if a["n_s"] else None} for c, a in acc.items()}


def _existing_scores(session: Session, cells: list) -> dict:
    rows = session.execute(text("""
        SELECT h3_cell, CAST(risk_score AS FLOAT) rs FROM canonical_scores
        WHERE hazard_type='coastal_erosion' AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL
          AND h3_cell = ANY(:cells)
    """), {"sc": SCENARIO, "h": HORIZON, "cells": cells}).all()
    return {c: float(s) for c, s in rows}


def _run(session: Session) -> ValidationResult:
    if not TARGET_CSV.exists():
        return ValidationResult(hazard_type="coastal_erosion", kind="rank", predicted=[], observed=[], labels=[],
                                target_source=TARGET, scope="global", method="out_of_sample",
                                notes=f"target file {TARGET_CSV} not present — run scripts/fetch_shoreline_change.py")
    import pandas as pd

    from ml.scoring.coastal_erosion_point import score_coastal_erosion_point

    d = pd.read_csv(TARGET_CSV, encoding="latin-1")
    rows = ({"lat": la, "lon": lo, "rate": r, "n_shorelines": n, "linearity": lin}
            for la, lo, r, n, lin in zip(d.Intercept_lat, d.Intercept_lon, d.coeflm, d.nb_shorelines, d.cor_classes_1))
    cells = aggregate_transects(rows)
    ids = sorted(cells)
    scores = _existing_scores(session, ids)
    n_pre = len(scores)
    n_demand = n_inland = 0
    for c in ids:
        if c in scores:
            continue
        lat, lon = h3.cell_to_latlng(c)
        r = score_coastal_erosion_point(lat, lon, scenario=SCENARIO, horizon=HORIZON)
        if r.get("status") in ("scored", "cached_hit") and r.get("risk_score") is not None:
            scores[c] = float(r["risk_score"]); n_demand += 1
        else:
            n_inland += 1                     # no modelled sandy coast in the cell — absent, never filled
    pred, obs, labels = [], [], []
    ps, os_ = [], []
    for c in ids:
        if c not in scores:
            continue
        pred.append(scores[c]); obs.append(cells[c]["obs"]); labels.append(f"{c} n={cells[c]['n']}")
        if cells[c]["obs_strong"] is not None:
            ps.append(scores[c]); os_.append(cells[c]["obs_strong"])
    import numpy as np
    sp_strong = M.spearman(np.asarray(ps, float), np.asarray(os_, float)) if len(ps) >= M.MIN_N else None
    n_tr = int(sum(cells[c]["n"] for c in ids if c in scores))
    return ValidationResult(
        hazard_type="coastal_erosion", kind="rank", predicted=pred, observed=obs, labels=labels,
        target_source=TARGET, scope="global", horizon=HORIZON, method="out_of_sample",
        data_vintage=f"Landsat 1984–2016 trends vs LISCOAST {SCENARIO}×{HORIZON}"[:60],
        notes=(f"platform coastal_erosion score ({SCENARIO}×{HORIZON}; the channel has no baseline lane) at the transect's "
               f"res-8 cell vs the observed mean shoreline change rate of the cell's transects (m/yr, erosion positive); "
               f"{len(pred)} cells from {n_tr} transects; {n_pre} cells had a platform score already, {n_demand} scored on demand "
               f"via the point scorer, {n_inland} transect cells had no modelled sandy coast and are absent; "
               f"strong-linear-trend subset Spearman={sp_strong} over {len(ps)} cells. The projection's ambient term "
               f"derives from the same Landsat trend product, so this tests delivered-score fidelity, not an independent lineage."),
        extra={"n_transects": n_tr, "n_cells_prescored": n_pre, "n_cells_on_demand": n_demand,
               "n_cells_no_coast": n_inland, "spearman_strong_linear": None if sp_strong is None else round(sp_strong, 4),
               "n_cells_strong_linear": len(ps), "scenario": SCENARIO, "horizon": HORIZON},
    )


register("coastal_erosion_shoreline")(_run)
