"""Subsidence v2 (observed EGMS rate), held out in time — does the sinking measured in 2020–2021 predict the sinking
measured in 2022–2024 at the same place?

Uses the per-point EGMS time series (6-day epochs, mm; `scripts/fetch_egms_tiles.py --keep-csv`). Per point, an OLS
rate is fitted on epochs ≤ SPLIT and, separately, on epochs > SPLIT. Points are grouped into H3 res-8 cells (the
channel's own unit) and the cell statistic is the same one the channel publishes: the 90th percentile of the
subsidence rate. Prediction = the channel score from the EARLY rate; observed = the LATE rate. `rank` kind, gate
Spearman ≥ 0.35 with monotone bands, fixed random sample of cells (seed stated). The glacial-rebound region is
excluded as in the class test (uplift is not subsidence). Scope: EGMS coverage (EEA states).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session

from ml.scoring.subsidence_egms import MIN_PIXELS, PCT, rate_to_score
from services.validation.engine import ValidationResult, register

TILES = Path("data/egms")
SPLIT = "20211231"
SAMPLE, SEED = 200_000, 7
REBOUND = (55.0, 4.0, 35.0)
MIN_EPOCHS = 40


def _rates(csv: Path):
    """(lon, lat, early_rate, late_rate) per point, rates in mm/yr with sinking positive."""
    import pandas as pd
    from pyproj import Transformer
    head = pd.read_csv(csv, nrows=0).columns
    dates = [c for c in head if c.isdigit() and len(c) == 8]
    early, late = [d for d in dates if d <= SPLIT], [d for d in dates if d > SPLIT]
    if len(early) < MIN_EPOCHS or len(late) < MIN_EPOCHS:
        return None
    d = pd.read_csv(csv, usecols=["easting", "northing"] + dates, dtype="float32")
    tr = Transformer.from_crs("EPSG:3035", "EPSG:4326", always_xy=True)
    lon, lat = tr.transform(d.easting.values.astype(float), d.northing.values.astype(float))

    def slope(cols):
        t = np.array([(pd.Timestamp(c) - pd.Timestamp("2020-01-01")).days / 365.25 for c in cols])
        y = d[cols].values.astype("float64")
        t0 = t - t.mean()
        return (y - y.mean(axis=1, keepdims=True)) @ t0 / (t0 @ t0)      # OLS slope, mm/yr, per point
    return np.asarray(lon), np.asarray(lat), -slope(early), -slope(late)


def _run(session: Session) -> ValidationResult:
    import h3
    csvs = sorted(TILES.glob("EGMS_L3_*_U_2020_2024_1.csv"))
    if not csvs:
        return ValidationResult(hazard_type="subsidence", kind="rank", predicted=[], observed=[], labels=[],
                                target_source="Copernicus EGMS point time series 2022–2024 (held out)", scope="EU", method="temporal_holdout",
                                notes="no EGMS time-series CSVs under data/egms — run scripts/fetch_egms_tiles.py --keep-csv")
    cells: dict[str, list] = {}
    for csv in csvs:
        got = _rates(csv)
        if got is None:
            continue
        lon, lat, e, lt = got
        keep = ~((lat > REBOUND[0]) & (lon >= REBOUND[1]) & (lon <= REBOUND[2])) & np.isfinite(e) & np.isfinite(lt)
        for la, lo, ee, ll in zip(lat[keep], lon[keep], e[keep], lt[keep]):
            cells.setdefault(h3.latlng_to_cell(float(la), float(lo), 8), []).append((ee, ll))
    keys = [k for k, v in cells.items() if len(v) >= MIN_PIXELS]
    if len(keys) > SAMPLE:
        keys = [keys[i] for i in np.sort(np.random.default_rng(SEED).choice(len(keys), SAMPLE, replace=False))]
    pred, obs = [], []
    for k in keys:
        a = np.asarray(cells[k])
        pred.append(rate_to_score(float(np.percentile(a[:, 0], PCT)))); obs.append(float(np.percentile(a[:, 1], PCT)))
    return ValidationResult(hazard_type="subsidence", kind="rank", predicted=pred, observed=obs, labels=keys,
                            target_source="Copernicus EGMS InSAR point time series: subsidence rate fitted on 2022–2024 epochs (held out)",
                            scope="EU", method="temporal_holdout", data_vintage=f"EGMS 2020–2024, {len(csvs)} tiles, seed {SEED}",
                            notes=(f"v2 cell score from the rate fitted on epochs ≤ {SPLIT} vs the {PCT}th-percentile rate the same cell's points showed "
                                   f"after it; {len(pred)} cells with ≥ {MIN_PIXELS} points, glacial-rebound region excluded; out of sample in time"),
                            extra={"n_tiles": len(csvs), "n_cells_total": len(cells)})


register("subsidence_egms_holdout")(_run)
