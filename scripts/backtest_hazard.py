"""
Honest backtest for a hazard model.

The training AUC was computed on a RANDOM train/test split. Because all labeled
rows come from a single event (the same handful of days), and the same H3 cell
appears on consecutive days, a random split lets the model memorise cells — train
sees cell X on day 1, test asks about cell X on day 2 with near-identical
features. The result is an inflated number that reflects in-event interpolation,
not skill.

This script re-measures with a SPATIAL split: GroupKFold grouped by h3_cell, so
no cell is ever in both train and test. The out-of-fold AUC / average-precision
is the honest estimate of how well the model generalises to UNSEEN locations
within the event.

Caveat printed in the output: this is still within ONE event. It does NOT
establish forecasting skill for a future/different event — that needs multiple
independent labeled events, which the data does not yet contain.

Usage:  python scripts/backtest_hazard.py flood
        python scripts/backtest_hazard.py wildfire
"""
import sys
import warnings

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold, train_test_split

warnings.filterwarnings("ignore")

from sqlalchemy import text

from core.db.session import get_session
from ml.scoring.ensemble import EnsembleScorer

HAZARDS = {
    "flood": {
        "table": "ml_features_flood", "label": "flood_occurred",
        "features": ["precipitation_7d_mm", "soil_saturation_index", "glofas_discharge_m3s"],
        "pos_weight": 10.0,
    },
    "wildfire": {
        "table": "ml_features_wildfire", "label": "fire_occurred",
        "features": ["gfs_wind_speed_ms", "gfs_relative_humidity_pct", "days_since_last_rain"],
        "pos_weight": 8.0,
    },
}


def load(cfg):
    cols = ", ".join(f"CAST({c} AS FLOAT) AS {c}" for c in cfg["features"])
    sql = text(f"""
        SELECT h3_cell, observed_at::date AS d, {cols}, {cfg['label']}::int AS y
        FROM   {cfg['table']}
        WHERE  {cfg['label']} IS NOT NULL
    """)
    with get_session() as s:
        return pd.DataFrame(s.execute(sql).mappings().all())


def fit_score(train_df, test_df, feats, pw):
    sc = EnsembleScorer(scale_pos_weight=pw)
    sc.fit(train_df[feats].values, train_df["y"].values.astype(int), feature_cols=feats)
    return (sc.score_dataframe(test_df[feats].copy())["score"] / 100.0).values


def recall_at_k(y, scores, k):
    order = np.argsort(-scores)
    topk = set(order[:k].tolist())
    pos = set(np.where(y == 1)[0].tolist())
    return len(topk & pos) / max(1, len(pos))


def main():
    hazard = sys.argv[1] if len(sys.argv) > 1 else "flood"
    cfg = HAZARDS[hazard]
    df = load(cfg)
    feats, y = cfg["features"], df["y"].values.astype(int)
    n_pos = int(y.sum())
    n_cells_pos = df.loc[df.y == 1, "h3_cell"].nunique()
    n_days = df["d"].nunique()
    base_rate = y.mean()

    print(f"\n=== Backtest: {hazard} ===")
    print(f"rows={len(df):,}  positives={n_pos}  distinct positive cells={n_cells_pos}  "
          f"days={n_days}  base_rate={base_rate:.5f}")

    # 1) RANDOM split (reproduces the inflated training number)
    tr, te = train_test_split(df, test_size=0.2, random_state=42, stratify=y)
    p_rand = fit_score(tr, te, feats, cfg["pos_weight"])
    auc_rand = roc_auc_score(te["y"], p_rand)
    ap_rand = average_precision_score(te["y"], p_rand)

    # 2) SPATIAL split — GroupKFold by h3_cell, pooled out-of-fold predictions
    gkf = GroupKFold(n_splits=5)
    oof = np.full(len(df), np.nan)
    for tr_idx, te_idx in gkf.split(df, y, groups=df["h3_cell"]):
        oof[te_idx] = fit_score(df.iloc[tr_idx], df.iloc[te_idx], feats, cfg["pos_weight"])
    auc_sp = roc_auc_score(y, oof)
    ap_sp = average_precision_score(y, oof)
    r_at_n = recall_at_k(y, oof, n_pos)              # recall@(#positives)

    print(f"\n  {'split':<24}{'ROC-AUC':>10}{'Avg-Prec':>12}")
    print(f"  {'random (inflated)':<24}{auc_rand:>10.4f}{ap_rand:>12.4f}")
    print(f"  {'spatial / by-cell (honest)':<24}{auc_sp:>10.4f}{ap_sp:>12.4f}")
    print(f"\n  baseline Avg-Prec (random guess) = {base_rate:.4f}")
    print(f"  spatial recall@{n_pos} (top-{n_pos} cells capture this share of real events) = {r_at_n:.2f}")
    print(f"\n  ⚠ Still ONE event ({n_days} days). Spatial CV tests generalisation to")
    print("    unseen LOCATIONS, not to a future EVENT. Forecasting skill is UNTESTED")
    print("    until multiple independent labeled events exist.\n")


if __name__ == "__main__":
    main()
