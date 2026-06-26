"""
Train the flood XGBoost model on the Rhine/Ahr 2021 historical backfill.

Prerequisites:
    1. scripts/backfill_historical.py       (satellite_observations populated)
    2. scripts/run_feature_pipeline_historical.py  (ml_features_flood populated)
    3. scripts/load_ground_truth_labels.py  (flood_occurred labels set)

Usage:
    python scripts/train_flood_model.py

    # Temporal split (recommended for validation integrity):
    #   train on July 5-13, test on July 14-15 (the actual flood days)
    python scripts/train_flood_model.py --train-end 2021-07-13 --test-start 2021-07-14
"""
import argparse
import logging
import sys
from datetime import date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-end",  default=None, help="Last training date (ISO, e.g. 2021-07-13)")
    parser.add_argument("--test-start", default=None, help="First test date  (ISO, e.g. 2021-07-14)")
    parser.add_argument("--no-register", action="store_true", help="Skip model_registry insert")
    args = parser.parse_args()

    from core.config import settings
    from ml.training.flood_model import train

    train_end  = date.fromisoformat(args.train_end)  if args.train_end  else None
    test_start = date.fromisoformat(args.test_start) if args.test_start else None

    logger.info("=" * 60)
    logger.info("  Flood XGBoost — training run")
    logger.info(f"  MLflow: {settings.MLFLOW_TRACKING_URI}")
    logger.info("=" * 60)

    try:
        result = train(
            train_end=train_end,
            test_start=test_start,
            mlflow_uri=settings.MLFLOW_TRACKING_URI,
            register=not args.no_register,
        )
    except ValueError as exc:
        logger.error(str(exc))
        sys.exit(1)

    logger.info("")
    logger.info("Training complete.")
    logger.info(f"  Model version : {result.model_version}")
    logger.info(f"  ROC-AUC       : {result.roc_auc:.4f}")
    logger.info(f"  Avg Precision : {result.avg_precision:.4f}")
    logger.info(f"  Train samples : {result.n_train}")
    logger.info(f"  Test samples  : {result.n_test}")
    logger.info("")
    logger.info("Next step: python scripts/validate_week10.py")


if __name__ == "__main__":
    main()
