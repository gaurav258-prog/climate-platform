"""
Three-model ensemble scorer.

Why three models:
  XGBoost     — primary, captures non-linear feature interactions, exact SHAP
  LightGBM    — cross-checker, different tree-building bias, fails differently
  Logistic    — sanity sentinel, flags out-of-distribution situations when it
                disagrees with the complex models

Published score  = ensemble mean  (0-100)
Confidence band  = 10th/90th percentile across the three model predictions
Ensemble JSONB   = {xgb: N, lgbm: N, logistic: N} stored with every score

The disagreement between models is the early-warning signal for unusual events
outside the training distribution — exactly the situations that matter most.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

logger = logging.getLogger(__name__)

try:
    import xgboost as xgb
    _XGB_AVAILABLE = True
except ImportError:
    _XGB_AVAILABLE = False
    logger.warning("xgboost not available — ensemble will use 2 models")

try:
    import lightgbm as lgb
    _LGB_AVAILABLE = True
except ImportError:
    _LGB_AVAILABLE = False
    logger.warning("lightgbm not available — ensemble will use 2 models")


@dataclass
class EnsembleResult:
    score: float            # 0-100, ensemble mean
    ci_lower: float         # 10th percentile
    ci_upper: float         # 90th percentile
    per_model: dict         # {xgb: N, lgbm: N, logistic: N}
    n_models: int
    high_disagreement: bool # std > 8 points — flag unusual situation


class EnsembleScorer:
    """
    Trains and scores using a 3-model ensemble.
    Call fit() once, then score_dataframe() for each scoring run.
    """

    DISAGREEMENT_THRESHOLD = 8.0  # std dev in score points (0-100)

    def __init__(self, scale_pos_weight: float = 10.0):
        self.scale_pos_weight = scale_pos_weight
        self._pipelines: dict[str, Pipeline] = {}
        self._feature_cols: list[str] = []

    # ── Build individual pipelines ────────────────────────────────

    def _make_xgb(self) -> Pipeline:
        clf = xgb.XGBClassifier(
            n_estimators=300,
            max_depth=4,
            learning_rate=0.05,
            scale_pos_weight=self.scale_pos_weight,
            subsample=0.8,
            colsample_bytree=0.8,
            eval_metric="logloss",
            random_state=42,
            n_jobs=-1,
            tree_method="hist",
        )
        return Pipeline([("imputer", SimpleImputer(strategy="median")), ("clf", clf)])

    def _make_lgbm(self) -> Pipeline:
        clf = lgb.LGBMClassifier(
            n_estimators=300,
            max_depth=4,
            learning_rate=0.05,
            scale_pos_weight=self.scale_pos_weight,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1,
            verbose=-1,
        )
        return Pipeline([("imputer", SimpleImputer(strategy="median")), ("clf", clf)])

    def _make_logistic(self) -> Pipeline:
        clf = LogisticRegression(
            C=1.0,
            max_iter=1000,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )
        return Pipeline([("imputer", SimpleImputer(strategy="median")), ("clf", clf)])

    # ── Training ─────────────────────────────────────────────────

    def fit(self, X_train: np.ndarray, y_train: np.ndarray,
            feature_cols: list[str]) -> "EnsembleScorer":
        self._feature_cols = feature_cols

        candidates = {"logistic": self._make_logistic()}
        if _XGB_AVAILABLE:
            candidates["xgb"] = self._make_xgb()
        if _LGB_AVAILABLE:
            candidates["lgbm"] = self._make_lgbm()

        for name, pipe in candidates.items():
            logger.info(f"[Ensemble] training {name} ...")
            pipe.fit(X_train, y_train)
            self._pipelines[name] = pipe

        logger.info(f"[Ensemble] {len(self._pipelines)} models trained: {list(self._pipelines)}")
        return self

    # ── Scoring ───────────────────────────────────────────────────

    def score_array(self, X: np.ndarray) -> list[EnsembleResult]:
        """Score a 2D feature array, return one EnsembleResult per row."""
        if not self._pipelines:
            raise RuntimeError("EnsembleScorer.fit() must be called before score_array()")

        # Collect probability from each model
        probs: dict[str, np.ndarray] = {
            name: pipe.predict_proba(X)[:, 1]
            for name, pipe in self._pipelines.items()
        }

        prob_matrix = np.stack(list(probs.values()), axis=0)  # (n_models, n_samples)
        means  = prob_matrix.mean(axis=0)
        stds   = prob_matrix.std(axis=0)
        p10    = np.percentile(prob_matrix, 10, axis=0)
        p90    = np.percentile(prob_matrix, 90, axis=0)

        model_names = list(probs.keys())

        results = []
        for i in range(X.shape[0]):
            per_model = {
                name: round(float(probs[name][i]) * 100, 1)
                for name in model_names
            }
            results.append(EnsembleResult(
                score=round(float(means[i]) * 100, 1),
                ci_lower=round(float(p10[i]) * 100, 1),
                ci_upper=round(float(p90[i]) * 100, 1),
                per_model=per_model,
                n_models=len(model_names),
                high_disagreement=bool(float(stds[i]) * 100 > self.DISAGREEMENT_THRESHOLD),
            ))
        return results

    def score_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Score a DataFrame using self._feature_cols.
        Returns df with added columns: score, ci_lower, ci_upper,
        ensemble_scores (dict), high_disagreement.
        """
        active = [c for c in self._feature_cols if c in df.columns]
        X = df[active].values
        results = self.score_array(X)

        df = df.copy()
        df["score"]              = [r.score for r in results]
        df["ci_lower"]           = [r.ci_lower for r in results]
        df["ci_upper"]           = [r.ci_upper for r in results]
        df["ensemble_scores"]    = [r.per_model for r in results]
        df["high_disagreement"]  = [r.high_disagreement for r in results]
        return df

    # ── SHAP (XGBoost only — exact values) ──────────────────────

    def shap_values(self, X: np.ndarray) -> dict | None:
        """
        Return SHAP values from the XGBoost model only (exact, not approximate).
        Returns dict {feature_name: mean_abs_shap} or None if XGBoost unavailable.
        """
        if "xgb" not in self._pipelines:
            return None
        try:
            import shap
            xgb_clf = self._pipelines["xgb"].named_steps["clf"]
            explainer = shap.TreeExplainer(xgb_clf)
            imputer   = self._pipelines["xgb"].named_steps["imputer"]
            X_imp     = imputer.transform(X)
            vals      = explainer.shap_values(X_imp)
            mean_abs  = np.abs(vals).mean(axis=0)
            return dict(zip(self._feature_cols, mean_abs.tolist()))
        except Exception as exc:
            logger.warning(f"[Ensemble] SHAP computation failed: {exc}")
            return None
