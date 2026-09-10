"""Anchor the severe-convective potential to observed DAMAGING-event frequency (NOAA SPC hail ≥ 1 in, wind ≥ 50 kt
or unmeasured severe-wind reports, tornadoes) — the step that turns an environment index into a hazard scale.

The potential (sqrt(2·CAPE)·shear, Taszarek WMAXSHEAR) says where severe-convective environments are common; it
says nothing about how often damaging events actually occur. Here we fit, on CONUS, the monotone relation
potential → expected annual damaging reports per 10⁴ km² on 2000–2013 and test it out of time on 2014–2023
(rank correlation across cells + AUC for 'at least one damaging report every two years'). The fitted relation is
written to data/convective/convective_anchor.json and read by the v2 scorer; the scale's anchors are ABSOLUTE
frequencies (reports · yr⁻¹ · 10⁻⁴ km⁻²), not a percentile of land. Reports are population-biased (disclosed);
outside CONUS the relation is a transfer through the same environment field (disclosed; ESWD is not licensed).
Run:  PYTHONPATH=. .venv/bin/python scripts/anchor_convective_spc.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score

GRID = Path("data/convective/convective_potential.npz")
OUT = Path("data/convective/convective_anchor.json")
CONUS = (24.5, 49.5, -124.5, -67.0)
TRAIN, TEST = (2000, 2013), (2014, 2023)
# The target is the ANNUAL PROBABILITY that the cell (0.25°, ~600 km²) sees at least one damaging report — bounded,
# and not inflated by the dozens of reports one storm generates. The scale is that probability itself: score = 100·p.


def load_reports() -> pd.DataFrame:
    frames = []
    hail = pd.read_csv("data/convective/1955-2023_hail.csv", usecols=["yr", "mag", "slat", "slon"])
    frames.append(hail[hail["mag"] >= 1.0].assign(kind="hail"))
    wind = pd.read_csv("data/convective/1955-2023_wind.csv", usecols=["yr", "mag", "slat", "slon"])
    frames.append(wind[(wind["mag"] >= 50) | (wind["mag"] == 0)].assign(kind="wind"))     # 0 = severe, speed unmeasured
    tor = pd.read_csv("data/convective/spc_tornadoes.csv", usecols=["yr", "slat", "slon"])
    frames.append(tor.assign(mag=np.nan, kind="tornado"))
    df = pd.concat(frames, ignore_index=True)
    df = df[(df.yr >= TRAIN[0]) & (df.yr <= TEST[1]) & df.slat.between(CONUS[0], CONUS[1]) & df.slon.between(CONUS[2], CONUS[3])]
    return df


def main() -> None:
    g = np.load(GRID); lat, lon, pot = g["lat"], g["lon"], g["potential"]
    dlat = float(abs(np.diff(lat).mean())); dlon = float(abs(np.diff(lon).mean()))
    la_i = np.where((lat >= CONUS[0]) & (lat <= CONUS[1]))[0]; lo_i = np.where((lon >= CONUS[2]) & (lon <= CONUS[3]))[0]
    sub = pot[np.ix_(la_i, lo_i)]
    land = ~np.isnan(sub)
    # cell area is not needed: the target is a probability per cell, not a density
    df = load_reports()
    print(f"reports {TRAIN[0]}–{TEST[1]} in CONUS: {len(df):,} ({df.kind.value_counts().to_dict()}) · grid {dlat:.2f}°×{dlon:.2f}° · {land.sum():,} land cells")

    def density(years):
        """annual probability of ≥1 damaging report in the cell: years-with-a-report / years"""
        d = df[(df.yr >= years[0]) & (df.yr <= years[1])]
        ii = np.clip(np.round((d.slat.values - lat[la_i][0]) / (lat[la_i][1] - lat[la_i][0])).astype(int), 0, len(la_i) - 1)
        jj = np.clip(np.round((d.slon.values - lon[lo_i][0]) / (lon[lo_i][1] - lon[lo_i][0])).astype(int), 0, len(lo_i) - 1)
        hit = np.zeros(sub.shape)
        for yr in range(years[0], years[1] + 1):
            m = (d.yr.values == yr); cnt = np.zeros(sub.shape); np.add.at(cnt, (ii[m], jj[m]), 1); hit += (cnt > 0)
        return hit / (years[1] - years[0] + 1)

    tr, te = density(TRAIN), density(TEST)
    x = sub[land]; y_tr = tr[land]; y_te = te[land]
    iso = IsotonicRegression(y_min=0.0, increasing=True, out_of_bounds="clip").fit(x, y_tr)
    pred = iso.predict(x)
    rho_raw = spearmanr(x, y_te).correlation
    rho_fit = spearmanr(pred, y_te).correlation
    auc = roc_auc_score((y_te >= 0.5).astype(int), pred)
    print(f"held-out {TEST[0]}–{TEST[1]}: Spearman(potential, observed) = {rho_raw:.3f} · Spearman(fitted, observed) = {rho_fit:.3f} · AUC(damaging event in ≥ half the years) = {auc:.3f}")
    print("observed p quantiles (test):", {q: round(float(np.quantile(y_te, q)), 2) for q in (0.25, 0.5, 0.75, 0.9)})
    grid_x = np.arange(0, 101, 2.0); grid_y = iso.predict(grid_x)
    print("potential → annual probability of a damaging event:", {int(a): round(float(b), 3) for a, b in zip(grid_x[::10], grid_y[::10])})
    OUT.write_text(json.dumps({"source": "NOAA SPC hail ≥1 in, severe wind, tornado reports; CONUS", "train_years": TRAIN, "test_years": TEST,
                               "n_reports": int(len(df)), "held_out": {"spearman_raw": round(float(rho_raw), 3), "spearman_fitted": round(float(rho_fit), 3), "auc_event_most_years": round(float(auc), 3)},
                               "mapping": {"potential": grid_x.tolist(), "annual_probability": [round(float(v), 4) for v in grid_y]},
                               "scale": "score = 100 × annual probability of at least one damaging severe-convective report in the ~600 km² cell",
                               "disclosure": "Report density is population-biased; the fit is CONUS-only and applied elsewhere as a transfer through the same environment field."}, indent=1))
    print("wrote", OUT)
    # the held-out result goes on the validation ledger so the model-risk register and the coverage map read it
    try:
        from core.db.session import get_session
        from services.validation.engine import ValidationResult, record_result
        with get_session() as s:
            rec = record_result(s, ValidationResult(hazard_type="severe_convective", kind="discrimination", predicted=[float(v) for v in pred], observed=[int(v >= 0.5) for v in y_te],
                                                    target_source=f"NOAA SPC hail ≥1 in / severe wind / tornado reports {TEST[0]}–{TEST[1]} (CONUS), damaging event in ≥ half the years",
                                                    scope="CONUS", method="temporal_holdout", data_vintage=f"{TRAIN[0]}–{TEST[1]}",
                                                    notes="potential → annual probability fitted on 2000–2013 (isotonic), tested out of time; population-biased reports disclosed"),
                                actor="anchor_convective_spc")
            s.commit()
        print("ledger:", rec.get("grade"), rec.get("passed"), {k: rec.get(k) for k in ("run_id",)})
    except Exception as e:
        print("ledger not written:", type(e).__name__, e)


if __name__ == "__main__":
    main()
