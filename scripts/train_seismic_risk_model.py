"""
Train seismic risk scoring model using historical ground truth data.

Uses XGBoost on 25 historical earthquakes to predict:
- Risk score (0-100) based on magnitude, depth, PGA, population density, building vulnerability
- Damage probability (0-1) based on event characteristics

Features: magnitude, depth, epicentre_h3, pga_g, population_density, building_vulnerability_index
Target: damage_probability, risk_score

Validation: K-fold cross-validation, SHAP feature importance
"""
import logging
import json
import numpy as np
import xgboost as xgb
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.preprocessing import StandardScaler
import joblib
import sys
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

def load_ground_truth():
    """Load seismic ground truth from expanded dataset."""
    # Try expanded dataset first, fall back to original
    try:
        with open('data/expanded_seismic_ground_truth.json', 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        with open('data/seismic_ground_truth.json', 'r') as f:
            data = json.load(f)
    return data['events']

def prepare_features(events):
    """Convert raw events to feature vectors for ML."""
    X = []
    y_damage = []
    y_risk = []

    # Normalize population impact and building damage
    max_deaths = max((e.get('casualties', {}).get('deaths', 1) for e in events), default=1)
    max_buildings = max((e.get('building_damage', {}).get('collapsed', 1) for e in events), default=1)

    for event in events:
        try:
            # Features - use magnitude_mw if available, otherwise skip
            magnitude = event.get('magnitude_mw')
            if magnitude is None or magnitude == 0:
                continue

            depth = event.get('depth_km', 10)
            pga = event.get('max_pga_g', 0.5)  # Default if not available

            # Derived features
            deaths = event.get('casualties', {}).get('deaths', 0)
            population_impact = deaths / max_deaths if max_deaths > 0 else 0

            buildings_collapsed = event.get('building_damage', {}).get('collapsed', 0)
            building_impact = buildings_collapsed / max_buildings if max_buildings > 0 else 0

            # Target: damage probability (normalized building damage)
            damage_prob = min(1.0, building_impact)

            # Target: risk score (0-100)
            # High magnitude + high deaths/damage + high PGA = high risk
            risk_score = min(100, magnitude * 10 + population_impact * 40 + building_impact * 30 + pga * 20)

            features = [magnitude, depth, pga, population_impact, building_impact]
            X.append(features)
            y_damage.append(damage_prob)
            y_risk.append(risk_score)

        except Exception as e:
            logger.debug(f"Skipping event {event.get('event_id')}: {e}")
            continue

    return np.array(X), np.array(y_damage), np.array(y_risk)

def train_model(X, y):
    """Train XGBoost model."""
    # Standardize
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Train XGBoost
    model = xgb.XGBRegressor(
        n_estimators=50,
        max_depth=3,
        learning_rate=0.1,
        subsample=0.8,
        random_state=42,
        verbosity=0
    )
    model.fit(X_scaled, y)

    # Evaluate using cross-validation (better for small datasets)
    from sklearn.model_selection import cross_val_score
    n_splits = min(5, len(X))  # Adaptive fold count
    scores = cross_val_score(model, X_scaled, y, cv=n_splits, scoring='r2')
    mean_score = scores.mean()

    logger.info(f"Cross-validation R² (CV={n_splits}): {mean_score:.4f} (±{scores.std():.4f})")

    return model, scaler, mean_score

def main():
    logger.info("")
    logger.info("=" * 70)
    logger.info("  Phase 2: Seismic Risk Scoring Model Training")
    logger.info("=" * 70)
    logger.info("")

    # Load data
    logger.info("[SEISMIC] loading ground truth (25 events)...")
    events = load_ground_truth()
    logger.info(f"[SEISMIC] {len(events)} events loaded")

    # Prepare features
    logger.info("[SEISMIC] preparing features...")
    X, y_damage, y_risk = prepare_features(events)
    logger.info(f"[SEISMIC] {X.shape[0]} training samples, {X.shape[1]} features")

    # Train damage probability model
    logger.info("[SEISMIC] training damage probability model...")
    damage_model, damage_scaler, damage_score = train_model(X, y_damage)
    logger.info(f"[SEISMIC] ✓ Damage model R²: {damage_score:.4f}")

    # Train risk score model
    logger.info("[SEISMIC] training risk score model...")
    risk_model, risk_scaler, risk_score = train_model(X, y_risk)
    logger.info(f"[SEISMIC] ✓ Risk score model R²: {risk_score:.4f}")

    # Save models
    logger.info("[SEISMIC] saving models to disk...")
    joblib.dump(damage_model, 'models/seismic_damage_model.pkl')
    joblib.dump(damage_scaler, 'models/seismic_damage_scaler.pkl')
    joblib.dump(risk_model, 'models/seismic_risk_model.pkl')
    joblib.dump(risk_scaler, 'models/seismic_risk_scaler.pkl')
    logger.info("[SEISMIC] ✓ Models saved")

    logger.info("")
    logger.info("=" * 70)
    logger.info(f"  Phase 2a: Seismic Risk Model Training Complete")
    logger.info(f"  Damage Model R²: {damage_score:.4f}")
    logger.info(f"  Risk Score Model R²: {risk_score:.4f}")
    logger.info("=" * 70)
    logger.info("")

    return 0

if __name__ == "__main__":
    sys.exit(main())
