"""
Week 10 Validation Gate.

Trains the flood model on Rhine/Ahr 2021 event data (July 14-15 flood peak),
then runs inference on PRECURSOR days (July 12, 2021 — 2 days before the peak)
to prove the platform could have issued an early warning.

Pass criteria:
  - ≥70% of known Ahr valley H3 cells score MEDIUM/HIGH/VERY_HIGH on July 12, 2021
  - ≥80% of Gironde wildfire cells score LOW for flood risk (specificity check)

This script is self-contained — it trains, scores, and reports in one run.

Usage:
    python scripts/validate_week10.py
    python scripts/validate_week10.py --precursor-date 2021-07-12
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

import h3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Ground truth cells for Ahr valley (same polygon as load_ground_truth_labels.py)
_AHR_VALLEY_POLY = {
    "type": "Polygon",
    "coordinates": [[
        [6.60, 50.41], [6.70, 50.45], [6.85, 50.50], [6.95, 50.56],
        [7.05, 50.59], [7.15, 50.61], [7.30, 50.61],
        [7.30, 50.50], [7.15, 50.50], [7.05, 50.47], [6.95, 50.45],
        [6.85, 50.42], [6.70, 50.36], [6.60, 50.31],
        [6.60, 50.41],
    ]],
}

_GIRONDE_POLYS = [
    {"type": "Polygon", "coordinates": [[[-1.22, 44.52], [-0.82, 44.52], [-0.82, 44.78], [-1.22, 44.78], [-1.22, 44.52]]]},
    {"type": "Polygon", "coordinates": [[[-0.72, 44.38], [-0.22, 44.38], [-0.22, 44.68], [-0.72, 44.68], [-0.72, 44.38]]]},
]

PASS_THRESHOLD_RECALL = 0.70    # 70% of flood cells must score >= MEDIUM
PASS_THRESHOLD_SPEC   = 0.80    # 80% of Gironde cells must score LOW for flood


def _get_flood_cells() -> set[str]:
    return set(h3.geo_to_cells(_AHR_VALLEY_POLY, 8))


def _get_gironde_cells() -> set[str]:
    cells: set[str] = set()
    for poly in _GIRONDE_POLYS:
        cells.update(h3.geo_to_cells(poly, 8))
    return cells


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--precursor-date", default="2021-07-12",
                        help="Date to score as 'early warning' day (default: 2021-07-12)")
    parser.add_argument("--train-end",  default="2021-07-13")
    parser.add_argument("--test-start", default="2021-07-14")
    args = parser.parse_args()

    precursor_date = date.fromisoformat(args.precursor_date)
    train_end      = date.fromisoformat(args.train_end)
    test_start     = date.fromisoformat(args.test_start)

    from core.config import settings
    from ml.training.flood_model import (
        train, score_cells, load_labeled_features, _build_pipeline,
        FEATURE_COLS
    )

    logger.info("=" * 60)
    logger.info("  Week 10 Validation Gate")
    logger.info("=" * 60)
    logger.info(f"  Training on flood peak days: {test_start} → 2021-07-15")
    logger.info(f"  Scoring precursor date:       {precursor_date}")
    logger.info("")

    # ── Step 1: Train the model ──────────────────────────────────
    logger.info("STEP 1: Training XGBoost flood model ...")
    try:
        result = train(
            train_end=train_end,
            test_start=test_start,
            mlflow_uri=settings.MLFLOW_TRACKING_URI,
            register=False,  # validation run — don't register
        )
    except ValueError as exc:
        logger.error(f"Training failed: {exc}")
        sys.exit(1)

    # Re-load pipeline for inference (re-fit on full labeled dataset)
    import numpy as np
    import pandas as pd
    train_df, _ = load_labeled_features(train_end, test_start)
    active_features = [c for c in FEATURE_COLS if c in train_df.columns]
    pipe = _build_pipeline()
    pipe.fit(
        train_df[active_features].values,
        train_df["flood_occurred"].values.astype(int),
    )

    # ── Step 2: Score the precursor date ────────────────────────
    logger.info(f"\nSTEP 2: Scoring all cells for {precursor_date} ...")
    scored = score_cells(pipe, precursor_date, features=active_features)

    if scored.empty:
        logger.error(f"No feature rows for {precursor_date}. "
                     "Did you run run_feature_pipeline_historical.py?")
        sys.exit(1)

    logger.info(f"Scored {len(scored)} cells for {precursor_date}")

    # ── Step 3: Evaluate Ahr valley recall ──────────────────────
    logger.info("\nSTEP 3: Evaluating recall on Ahr valley cells ...")
    ahr_cells   = _get_flood_cells()
    gironde_cells = _get_gironde_cells()

    ahr_scored = scored[scored["h3_cell"].isin(ahr_cells)]
    gironde_scored = scored[scored["h3_cell"].isin(gironde_cells)]

    n_ahr = len(ahr_scored)
    n_ahr_at_risk = (ahr_scored["risk_bucket"].isin(["MEDIUM", "HIGH", "VERY_HIGH"])).sum()
    recall = n_ahr_at_risk / n_ahr if n_ahr > 0 else 0.0

    n_gironde = len(gironde_scored)
    n_gironde_low = (gironde_scored["risk_bucket"] == "LOW").sum()
    specificity = n_gironde_low / n_gironde if n_gironde > 0 else 0.0

    # ── Step 4: Print validation report ─────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("  VALIDATION REPORT — Week 10 Gate")
    logger.info("=" * 60)
    logger.info(f"  Model ROC-AUC (event days test):  {result.roc_auc:.4f}")
    logger.info(f"  Model Avg Precision:              {result.avg_precision:.4f}")
    logger.info("")
    logger.info(f"  ── Rhine / Ahr precursor recall ──────────────────────")
    logger.info(f"  Precursor date scored:     {precursor_date}")
    logger.info(f"  Ahr valley cells matched:  {n_ahr} / {len(ahr_cells)}")
    logger.info(f"  Cells scored MEDIUM+:      {n_ahr_at_risk} / {n_ahr}")
    logger.info(f"  Recall (≥MEDIUM):          {recall:.1%}")
    logger.info(f"  Target:                    ≥{PASS_THRESHOLD_RECALL:.0%}")
    recall_pass = recall >= PASS_THRESHOLD_RECALL
    logger.info(f"  Result:                    {'✓ PASS' if recall_pass else '✗ FAIL'}")

    logger.info("")
    logger.info(f"  ── Gironde specificity (no false flood alarms) ───────")
    logger.info(f"  Gironde fire cells matched: {n_gironde} / {len(gironde_cells)}")
    logger.info(f"  Cells scored LOW (correct): {n_gironde_low} / {n_gironde}")
    logger.info(f"  Specificity:               {specificity:.1%}")
    logger.info(f"  Target:                    ≥{PASS_THRESHOLD_SPEC:.0%}")
    spec_pass = specificity >= PASS_THRESHOLD_SPEC
    logger.info(f"  Result:                    {'✓ PASS' if spec_pass else '✗ FAIL'}")

    logger.info("")
    logger.info(f"  ── Risk bucket distribution (all {len(scored)} cells) ────")
    dist = scored["risk_bucket"].value_counts().to_dict()
    for bucket in ["VERY_HIGH", "HIGH", "MEDIUM", "LOW"]:
        count = dist.get(bucket, 0)
        bar = "█" * (count * 30 // len(scored)) if scored is not None and len(scored) > 0 else ""
        logger.info(f"  {bucket:12s}:  {count:7,}  {bar}")

    logger.info("")
    overall_pass = recall_pass and spec_pass
    if overall_pass:
        logger.info("  ✓ WEEK 10 VALIDATION GATE: PASSED")
    else:
        logger.info("  ✗ WEEK 10 VALIDATION GATE: NOT PASSED YET")

    logger.info("=" * 60)

    # Top 10 highest-risk cells (should be in the Ahr valley)
    logger.info("\nTop 10 highest-risk cells:")
    top10 = scored.nlargest(10, "risk_score")[["h3_cell", "risk_score", "risk_bucket"]]
    top10["in_ahr_valley"] = top10["h3_cell"].isin(ahr_cells)
    logger.info(top10.to_string(index=False))

    # Write scored cells to a CSV for inspection
    out_path = f"data/validation_scores_{precursor_date}.csv"
    import os
    os.makedirs("data", exist_ok=True)
    scored["in_ahr_valley"] = scored["h3_cell"].isin(ahr_cells)
    scored["in_gironde_fire"] = scored["h3_cell"].isin(gironde_cells)
    scored.to_csv(out_path, index=False)
    logger.info(f"\nAll scores written to: {out_path}")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
