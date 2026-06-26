"""
Train heat stress risk ensemble model.

Usage:
    python scripts/train_heat_model.py
    python scripts/train_heat_model.py --train-end 2023-07-15 --test-start 2023-07-16
    python scripts/train_heat_model.py --no-register
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)


def parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train heat stress risk ensemble model")
    parser.add_argument("--train-end",   type=parse_date, help="Last date in training set (YYYY-MM-DD)")
    parser.add_argument("--test-start",  type=parse_date, help="First date in test set (YYYY-MM-DD)")
    parser.add_argument("--mlflow-uri",  default=None,    help="MLflow tracking URI (default: localhost:5001)")
    parser.add_argument("--no-register", action="store_true", help="Skip writing to model_registry")
    args = parser.parse_args()

    if bool(args.train_end) != bool(args.test_start):
        logger.error("--train-end and --test-start must both be provided or both omitted")
        sys.exit(1)

    from ml.training.heat_model import train

    logger.info("Starting heat stress ensemble training …")
    result = train(
        train_end=args.train_end,
        test_start=args.test_start,
        mlflow_uri=args.mlflow_uri or "http://localhost:5001",
        register=not args.no_register,
    )

    print(f"\n{'='*50}")
    print(f"  Model:         {result.model_version}")
    print(f"  ROC-AUC:       {result.roc_auc:.4f}")
    print(f"  Avg Precision: {result.avg_precision:.4f}")
    print(f"  Train rows:    {result.n_train:,}")
    print(f"  Test rows:     {result.n_test:,}")
    if result.feature_importance:
        print(f"\n  Feature importance (XGBoost):")
        for feat, imp in sorted(result.feature_importance.items(),
                                key=lambda x: x[1], reverse=True):
            bar = "█" * int(imp * 30)
            print(f"    {feat:<35} {imp:.4f}  {bar}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
