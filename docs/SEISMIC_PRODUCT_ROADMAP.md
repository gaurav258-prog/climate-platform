# Seismic Product — Complete Implementation Roadmap
*Full product, CSEP-validated, ground truth from day 1, highest quality/completeness.*

## Dependency Graph & Critical Path

```
PHASE 0: Foundations (done in parallel with flood/wildfire)
├── ORM Models (SeismicEvent, DamageAssessment) → core/db/models.py
├── ESHM20 PGA loader script → scripts/load_eshm20_pga.py
└── Historical EMSC backfill (1990–present) → scripts/backfill_emsc_historical.py

PHASE 1: Ground Truth & Data (blocks ML training)
├── Seismic event labeling (2000–2026 European catalog with actual outcomes)
├── Ground truth damage observations (2021 Ahr, 2022 Gironde — synthetic SAR for now)
└── GNSS strain rate ingestion (EUREF EPN if available, else skip Phase 1.3)

PHASE 2: ML Models (3 parallel streams)
├── Seismic Risk Scoring Model (background hazard + catalog + population)
├── ETAS Aftershock Forecasting Model (catalog-only, CSEP-testable)
└── Precursor Signal Model (b-value, seismic quiescence, strain rate — if data ready)

PHASE 3: Validation & Operationalization
├── CSEP validation framework (prospective + retrospective evaluation)
├── Seismic scoring engine (daily canonical_scores writes)
└── Aftershock scoring engine (post-event probability updates)

PHASE 4: Backend (API + services)
├── API endpoints (events, risk-scores, damage-assessments, aftershock-forecast)
├── Real-time WebSocket for events
├── Parametric trigger design service (seismic index construction)
└── Alert feed integration (Operations view)

PHASE 5: Frontend (UI)
├── Seismic risk map layer (ESHM20 PGA background + forecast risk overlay)
├── Seismic events card (recent M≥4.5, clickable to detail)
├── Post-event damage assessment card (SAR damage probability map)
├── Aftershock forecast card (7-day, 30-day elevated-risk windows)
└── Parametric seismic trigger designer (Sidebar → Response section)
```

---

## Phase 0: Foundations (1.5 days) — START NOW IN PARALLEL

### 0.1 ORM Models
**File:** `core/db/models.py`
**What to add:**
```python
class SeismicEvent(Base):
    __tablename__ = "seismic_events"
    event_id: str = Column(Text, primary_key=True)
    magnitude: float = Column(Numeric(4, 2))
    mag_type: str = Column(String(10))  # 'Mw', 'ML', 'mb'
    depth_km: float = Column(Numeric(7, 2))
    epicentre_lat/lon: float = Column(Numeric(8, 5))
    epicentre_h3: str = Column(String(20))
    origin_time: datetime = Column(DateTime(tz=True))
    region_name: str = Column(Text)
    source_catalog: str = Column(String(50))  # 'EMSC', 'USGS', 'INGV'
    review_status: str = Column(String(20))  # 'reviewed', 'preliminary', 'automatic'
    damage_assessment_status: str = Column(String(30))
    ingested_at: datetime = Column(DateTime(tz=True), default=utcnow)
    
    # Relationships
    damage_assessments = relationship("DamageAssessment", back_populates="event")

class DamageAssessment(Base):
    __tablename__ = "damage_assessments"
    assessment_id: int = Column(Integer, Identity(always=True), primary_key=True)
    event_id: str = Column(Text, ForeignKey("seismic_events.event_id", ondelete='CASCADE'))
    h3_cell: str = Column(String(20))
    damage_probability: float = Column(Numeric(5, 4))
    log_ratio_db: float = Column(Numeric(8, 4))
    confidence: str = Column(String(10))
    distance_km: float = Column(Numeric(7, 2))
    method: str = Column(String(50))
    pre_pass_time/post_pass_time: datetime = Column(DateTime(tz=True))
    assessed_at: datetime = Column(DateTime(tz=True), default=utcnow)
    
    # Relationships
    event = relationship("SeismicEvent", back_populates="damage_assessments")
```
**Effort:** 1 hour
**Dependency:** None (can do now)

### 0.2 ESHM20 Static PGA Loader
**File:** `scripts/load_eshm20_pga.py`
**What it does:**
- Instantiate `SeismicHazardAdapter()`
- Fetch EU-wide PGA at H3 resolution 8
- Write to `satellite_observations` with hazard_type='seismic'
- Mark observed_at = ESHM20_RELEASE (2023-01-01)
- Run once, then verify count in DB

**Effort:** 1 hour
**Dependency:** ESHM20 adapter (already written)
**Command to run:**
```bash
python scripts/load_eshm20_pga.py
# Output: ~5,000–8,000 H3 cells across Europe with PGA values
```

### 0.3 Historical EMSC Backfill (1990–present)
**File:** `scripts/backfill_emsc_historical.py`
**What it does:**
- Query EMSC FDSN-event API for all events M≥4.5 from 1990 to today (~7,000–10,000 events)
- Paginate by year to avoid timeout
- Write to `seismic_events` table (not satellite_observations)
- Write to `satellite_observations` as event markers (hazard_type='seismic')

**Effort:** 2 hours (mostly waiting for API queries)
**Dependency:** EMSC adapter
**Expected output:** ~8,000 seismic_events rows spanning 35 years

---

## Phase 1: Ground Truth & Data (4 days) — IN PARALLEL with PHASE 0

### 1.1 Seismic Event Ground Truth Labeling
**What to do:**
Create a reference dataset of European seismic events (1990–2026) with:
- Magnitude, location, depth, origin time (from EMSC backfill)
- Actual deaths, injured, displaced, € economic loss (from NOAA NGDC, EM-DAT, national databases)
- Building damage extent (collapsed structures, uninhabitable buildings) — from USGS ShakeMaps where available
- Performance notes (was this event forecast-able a priori via precursor? aftershock sequence?)

**Key events to tag:**
- 1995 Kobe (M7.2) — baseline for precursor analysis
- 2009 L'Aquila (M6.3) — high-quality damage mapping available
- 2011 Christchurch-Darfield (M7.0) → aftershock M6.2 (3 weeks later) — ETAS test case
- 2016 Amatrice (M6.2) — Italy, damage well-documented
- 2016 Kaikōura (M7.8) → aftershocks (New Zealand, but CSEP data)
- 2019 Ridgecrest (M7.1) — aftershock sequence starting immediately
- 2023 Türkiye-Syria (M7.8 + M7.5) — 50K deaths, extensive damage mapping

**Output:** CSV or JSON file: `data/seismic_ground_truth.json`
```json
{
  "event_id": "emsc2009020109361340",
  "magnitude": 6.3,
  "region": "L'Aquila, Italy",
  "deaths": 309,
  "economic_loss_usd": 13_000_000_000,
  "buildings_collapsed": 5000,
  "max_intensity_mmi": 9,
  "damage_class_distribution": {"D0": 0.05, "D1": 0.08, "D2": 0.15, "D3": 0.32, "D4": 0.28, "D5": 0.12},
  "source": "USGS ShakeMap, NOAA NGDC, Italian Civil Protection"
}
```

**Effort:** 8 hours (research + data cleanup)
**Dependency:** None (can do now, in parallel)
**Tools:** NOAA NGDC, EM-DAT, USGS Earthquake Hazards, national disaster databases

### 1.2 Synthetic Ground Truth for 2021 Ahr & 2022 Gironde
**What to do:**
These were NOT seismic events, but we can use them to validate the SAR damage assessment pipeline:
- Generate synthetic pre/post SAR backscatter difference for the inundation zones
- Tag H3 cells in the flood extent as "damaged" (damage_probability = 0.7–1.0)
- Tag cells outside the flood extent as "not damaged" (damage_probability = 0.0–0.2)
- Run `services/processing/sar_coherence.py` against synthetic data
- Validate that the pipeline correctly identifies the inundation extent

**Output:** Test dataset in `data/synthetic_sar_damage.json`
**Effort:** 2 hours
**Dependency:** Flood extent data (from backfill)

### 1.3 GNSS Strain Rate Ingestion (if available)
**File:** `services/ingestion/adapters/euref_epn.py`
**What it does:**
- Query EUREF EPN (European Plate Observing System) for daily GPS/GNSS station positions
- Compute 30-day and 90-day strain rate per station (rate of change in station displacement)
- Map to H3 cells (multiple stations per cell, aggregate strain)
- Write to `satellite_observations` as hazard_type='seismic' with raw_value = strain_rate (nanostrains/day)

**Challenge:** EUREF EPN provides position time series, not pre-computed strain rates. May need to build strain computation.

**Effort:** 6–8 hours
**Dependency:** EUREF EPN API access, geodetic library (e.g., pyproj for coordinate transforms)
**If unavailable:** Defer to Phase 2.3; use catalog-only models for now

---

## Phase 2: ML Models (5 days) — PARALLEL

### 2.1 Seismic Risk Scoring Model
**File:** `scripts/train_seismic_model.py`
**What it does:**
Train an ML model (XGBoost or similar) to predict seismic risk score (0–100) per H3 cell.

**Input Features:**
```python
features = {
    "background_pga_g": raw_value from ESHM20,                    # continuous
    "building_vulnerability_class": from GEM OpenBuildingMap,      # categorical (A-F)
    "population_density": from WorldPop,                           # continuous
    "recent_seismic_activity_count": M≥4.5 in past 365 days,       # count
    "recent_magnitude_max": highest M in past 365 days,            # continuous
    "b_value_trend": from moment-frequency distribution slope,     # continuous (decreasing = precursor)
    "strain_rate_nanostrains_day": from EUREF if available,        # continuous
    "time_since_last_event_days": from closest historical event,   # continuous
    "fault_proximity_km": distance to major European fault,        # continuous
}
```

**Target Label:**
```python
target = "damage_extent_fraction"  # from ground truth: 0.0–1.0
# or binary: "damage_occurred" ∈ {0, 1}
```

**Training Data:**
- ~50–100 well-documented historical events (1995–2026)
- Per-event: compute features per H3 cell in affected region
- Per-cell: label with actual damage extent (from ShakeMaps, national reports)
- Cross-validation: 80% train, 20% test; stratify by magnitude

**Output:**
```
Model: seismic_risk_model_v1.pkl
Performance metrics: ROC-AUC, Brier score, information gain vs. Poisson baseline
Feature importances: SHAP values
```

**Effort:** 3 days
**Dependency:** Ground truth labels (Phase 1.1), GEM OpenBuildingMap download, WorldPop download

**Script skeleton:**
```python
# scripts/train_seismic_model.py
import pickle
from sklearn.ensemble import XGBClassifier
from core.db.session import get_session
import mlflow

# Load ground truth
ground_truth = load_seismic_ground_truth_labels()  # from Phase 1.1

# Feature engineering
features = extract_seismic_features_from_db()  # queries satellite_observations + seismic_events

# Train
model = XGBClassifier(max_depth=7, learning_rate=0.1, n_estimators=100)
model.fit(features, ground_truth["damage_occurred"])

# Log to MLflow
mlflow.log_model(model, "seismic_risk_model")
mlflow.log_metrics({
    "auc": roc_auc_score(...),
    "brier": brier_score_loss(...),
    "gain_vs_poisson": kl_divergence(...)
})

# Save
pickle.dump(model, open("ml/models/seismic_risk_model_v1.pkl", "wb"))
```

### 2.2 ETAS Aftershock Forecasting Model
**File:** `scripts/train_etas_model.py`
**What it does:**
Train an ETAS (Epidemic Type Aftershock Sequences) model on historical sequences.

**Input:**
- Mainshock events (M ≥ 6.5) from 1995–2026
- All aftershocks (M ≥ 4.5) within 30 days and 50 km of epicentre

**Output:**
Probability of M ≥ X aftershock in 7-day, 14-day, 30-day windows

**ETAS Parameters:**
```python
# Gutenberg-Richter
a_value = 0.95  # intercept (# events M≥5 per mainshock)
b_value = 1.0   # slope (magnitude distribution)

# Hawkes process
μ = 0.001       # background rate (events/day/cell)
K = 0.01        # triggering amplitude
α = 1.1         # temporal decay exponent
c = 0.05        # temporal offset (days)
d = 2.0         # spatial decay exponent
γ = 0.5         # spatial offset (km)
```

**Library:** Use `pyetas` or build custom Hawkes model (scikit-learn + scipy.optimize)

**Output:** ETAS model object + parameters + log-likelihood per test event
**Effort:** 2 days (code structure exists in literature)
**Dependency:** Historical catalog (EMSC backfill)

### 2.3 Precursor Signal Model (Optional, if GNSS available)
**File:** `scripts/train_precursor_model.py`
**What it does:**
If GNSS strain data is available, train a logistic regression or random forest to detect elevated seismic risk from:
- Strain rate acceleration
- Seismic quiescence (b-value decrease)
- Foreshock swarms (rate increase)

**Effort:** 1 day
**Dependency:** GNSS strain data (Phase 1.3); can defer if not available

---

## Phase 3: Validation & Operationalization (3 days)

### 3.1 CSEP Validation Framework
**File:** `services/validation/csep_evaluator.py`
**What it does:**
Implement CSEP evaluation metrics for the seismic risk and ETAS models:

```python
def csep_evaluate(forecast_catalog, observed_catalog, model_name, prediction_window):
    """
    Compute: Information gain, Brier score, log-likelihood, hit/miss rate, false alarm rate
    Compare: Our forecast vs. Poisson baseline vs. reference models (if available)
    Output: Evaluation table, confusion matrix, ROC curve
    """
    metrics = {
        "information_gain": info_gain(forecast_probs, observed_binary),
        "brier_score": brier_score_loss(forecast_probs, observed_binary),
        "log_likelihood": np.mean(np.log(forecast_probs[observed_binary] + 1e-10)),
        "auc_roc": roc_auc_score(observed_binary, forecast_probs),
        "confusion_matrix": confusion_matrix(observed_binary, forecast_binary),
        "skill_score": (hit_rate - false_alarm_rate) / (1 - false_alarm_rate),  # Hanssen-Kuipers
    }
    return metrics
```

**Effort:** 1.5 days
**Dependency:** Seismic Risk + ETAS models (Phase 2)
**Reference:** CSEP standard (https://www.corssa.org/display/CSEPDocs)

### 3.2 Seismic Scoring Engine
**File:** `scripts/run_seismic_scoring_engine.py`
**What it does:**
Daily job (like flood/wildfire):
1. Query latest EMSC events (past 24h)
2. For each event M ≥ 4.5: compute damage probability per affected H3 cell (via SAR coherence)
3. For each event M ≥ 6.0: run ETAS model → compute aftershock probability per cell/time window
4. Compute background seismic risk score per H3 cell (via seismic risk model)
5. Write canonical_scores with hazard_type='seismic'

**Pseudocode:**
```python
def run_seismic_scoring_engine():
    # 1. Get recent events
    recent_events = query_recent_emsc_events(hours=24)
    
    # 2. Damage assessment for M≥5.0
    for event in recent_events[recent_events.magnitude >= 5.0]:
        result = sar_coherence.run_damage_assessment(
            event_id=event.event_id,
            magnitude=event.magnitude,
            origin_time=event.origin_time,
            epicentre_lat=event.lat,
            epicentre_lon=event.lon,
        )
        # Write damage_assessments table
        write_damage_assessments(result)
    
    # 3. ETAS for M≥6.0
    for event in recent_events[recent_events.magnitude >= 6.0]:
        etas_probs = etas_model.forecast(
            mainshock=event,
            time_windows=[7, 14, 30],  # days
            magnitude_threshold=4.5,
        )
        # Write canonical_scores with model_id=etas_v1, time_horizon=7d/14d/30d
        for window_days, prob_map in etas_probs.items():
            write_canonical_scores(
                hazard_type='seismic',
                score_type='aftershock_probability',
                time_horizon=f'{window_days}d',
                prob_map=prob_map,
            )
    
    # 4. Background risk scores (daily refresh)
    risk_scores = seismic_risk_model.predict(
        features=extract_eu_features(),  # PGA, population, strain, etc.
    )
    write_canonical_scores(
        hazard_type='seismic',
        score_type='background_risk',
        time_horizon='current',
        risk_scores=risk_scores,
    )
```

**Effort:** 2 days
**Dependency:** Models (Phase 2), SAR coherence (already written), DB (Phase 0)

### 3.3 Aftershock Scoring Engine (Companion to 3.2)
Write aftershock probability updates to canonical_scores post-event. Already in 3.2.

---

## Phase 4: Backend Services (3 days)

### 4.1 API Endpoints
**File:** `api/routes/seismic.py`
```python
@router.get("/seismic/events")
async def get_seismic_events(
    startTime: datetime, endTime: datetime,
    magMin: float = 4.5, magMax: float = 9.0,
    limit: int = 100,
) -> list[SeismicEventResponse]:
    """List recent EMSC events with optional filtering."""
    events = session.query(SeismicEvent).filter(
        SeismicEvent.origin_time.between(startTime, endTime),
        SeismicEvent.magnitude.between(magMin, magMax),
    ).order_by(SeismicEvent.origin_time.desc()).limit(limit).all()
    return [SeismicEventResponse.from_orm(e) for e in events]

@router.get("/seismic/risk-scores")
async def get_seismic_risk_scores(
    cell: str = None, resolution: int = 8,
    scenario: str = "baseline",
) -> dict:
    """Current seismic risk scores per H3 cell."""
    scores = session.query(CanonicalScore).filter(
        CanonicalScore.hazard_type == 'seismic',
        CanonicalScore.scenario == scenario,
        CanonicalScore.valid_to.is_(None),  # latest only
    )
    if cell:
        scores = scores.filter(CanonicalScore.h3_cell == cell)
    return {s.h3_cell: s.risk_score for s in scores.limit(10000).all()}

@router.get("/seismic/damage-assessments")
async def get_damage_assessments(
    eventId: str = None, cell: str = None,
) -> list[DamageAssessmentResponse]:
    """Damage probability maps for specific events."""
    assessments = session.query(DamageAssessment)
    if eventId:
        assessments = assessments.filter(DamageAssessment.event_id == eventId)
    if cell:
        assessments = assessments.filter(DamageAssessment.h3_cell == cell)
    return [DamageAssessmentResponse.from_orm(a) for a in assessments.limit(5000).all()]

@router.get("/seismic/aftershock-forecast")
async def get_aftershock_forecast(
    eventId: str, timeWindow: str = "7d"  # or 14d, 30d
) -> dict:
    """Aftershock probability map for a mainshock."""
    scores = session.query(CanonicalScore).filter(
        CanonicalScore.hazard_type == 'seismic',
        CanonicalScore.model_version == 'etas_v1',
        CanonicalScore.time_horizon == timeWindow,
        # Link to event_id via observation_ids or a seismic_event_id column
    )
    return {...}

@router.websocket("/seismic/events/live")
async def websocket_seismic_events(websocket: WebSocket):
    """Real-time seismic event stream. Connects to monitor_seismic.py."""
    await websocket.accept()
    async for event in monitor_seismic.event_stream:
        await websocket.send_json(event.dict())
```

**Effort:** 1.5 days
**Dependency:** ORM models (Phase 0), scoring engines (Phase 3)

### 4.2 Real-Time Event Feed Integration
**Modification to** `scripts/monitor_seismic.py`:
- Post M≥5.0 events to a Redis pub/sub or direct WebSocket channel
- API endpoint subscribes and broadcasts to connected clients (React)

**Effort:** 0.5 days
**Dependency:** monitor_seismic.py (already written)

### 4.3 Parametric Seismic Trigger Design Service
**File:** `services/parametric/seismic_triggers.py`
```python
class SeismicTriggerDesigner:
    """Design parametric triggers for seismic indices."""
    
    def design_trigger(
        self,
        client_lat: float, client_lon: float,  # portfolio location
        coverage_region: str,                   # e.g., "Italy", "Greece"
        time_window_days: int = 7,              # 7-day elevated-risk window
        payout_threshold_prob: float = 0.60,    # trigger when aftershock prob > 60%
        design_fee_eur: float = 100_000,
    ) -> SeismicParametricPolicy:
        """
        Design a parametric policy:
        - Index: ETAS-based aftershock probability for 7 days post-mainshock
        - Trigger: Binary: aftershock prob > 60% in 7-day window → payout
        - Validation: Back-test against 20-year historical catalog
        - License fee: €80–200K annual
        """
        
        # 1. Back-test against historical aftershock sequences
        historical_sequences = self._get_historical_sequences(coverage_region)
        backtest_results = self._backtest_etas(
            historical_sequences, time_window_days, payout_threshold_prob
        )
        
        # 2. Compute basis risk
        basis_risk = self._compute_basis_risk(
            client_location=(client_lat, client_lon),
            historical_losses=client_losses,  # from underwriter
            forecast_triggers=backtest_results.triggers,
        )
        
        # 3. Design payout structure
        policy = SeismicParametricPolicy(
            index_name=f"ETAS-{coverage_region}-7d",
            trigger_threshold=payout_threshold_prob,
            payout_structure="binary" | "step-scaled",
            expected_trigger_frequency=backtest_results.hit_rate,
            basis_risk_score=basis_risk,
            design_fee=design_fee_eur,
            annual_license_fee=150_000,
            design_notes=backtest_results.summary,
        )
        return policy
```

**Effort:** 1.5 days
**Dependency:** ETAS model (Phase 2.2)

---

## Phase 5: Frontend (4 days)

### 5.1 Seismic Risk Map Layer
**File:** `ui/src/components/SeismicRiskLayer.jsx`
- Render H3 cells at resolution 8
- Color by seismic risk score: 0–20 (green) → 80–100 (red)
- Overlay on existing Risk Map
- Opacity slider to blend with flood/wildfire
- Tooltip: PGA (g), risk score, population, recent events in cell

**Effort:** 1.5 days
**Dependency:** Risk Map component (already exists)

### 5.2 Seismic Events Card
**File:** `ui/src/components/SeismicEventsCard.jsx`
- List recent M≥4.5 events (past 7 days)
- Card per event: magnitude, location, depth, time, region
- Color-code by magnitude (M4–5: yellow, M5–6: orange, M6+: red)
- Click to expand: detail panel with damage assessment status
- "View on map" link to center on epicentre

**Effort:** 1 day
**Dependency:** API endpoints (Phase 4), Operations view integration

### 5.3 Damage Assessment Panel
**File:** `ui/src/components/DamageAssessmentPanel.jsx`
- Post-event only (appears when M≥5.0 event + damage assessment ready)
- H3 map showing damage probability per cell
- Color gradient: 0.0 (blue) → 0.5 (orange) → 1.0 (red)
- Summary stats: cells damaged, population affected, estimated economic loss (rough estimate)
- Toggle: overlay with building density / population / past earthquake exposure

**Effort:** 1.5 days
**Dependency:** Damage assessment API (Phase 4.1)

### 5.4 Aftershock Forecast Card
**File:** `ui/src/components/AftershockForecastCard.jsx`
- Post-mainshock (M≥6.0) only
- 3 time windows: 7-day, 14-day, 30-day
- Probability map per window: cells with >50% M≥4.5 aftershock probability
- Summary: "N aftershocks expected per window" (mean count from ETAS)
- Historical context: "In 20 similar events, aftershocks occurred X% of the time"

**Effort:** 1 day
**Dependency:** ETAS API (Phase 4.1)

### 5.5 Parametric Seismic Trigger Designer
**File:** `ui/src/pages/ParametricSeismicPage.jsx`
- Sidebar → Response → "Parametric" menu, add "Seismic" sub-item
- Design form:
  - Select region (Italy, Greece, Romania, Balkans, etc.)
  - Select time window (7d, 14d, 30d, custom)
  - Select payout threshold (aftershock probability needed to trigger)
  - Back-test results: hit rate, false alarm rate, basis risk
  - Annual license fee estimate
- "Save design" → export as PDF or JSON

**Effort:** 1.5 days
**Dependency:** Parametric trigger design API (Phase 4.3)

### 5.6 Sidebar Navigation Update
**File:** `ui/src/components/Sidebar.jsx`
- Add "Seismic" to Monitoring section (alongside Flood/Wildfire/Heat)
- Badge: "Recent events" count (M≥4.5 in past 7 days)
- Sub-items: "Events", "Risk Map", "Damage Assessment", "Aftershock Forecast" (if applicable)

**Effort:** 0.5 days
**Dependency:** Sidebar component (already exists)

---

## Timeline & Effort Summary

| Phase | Description | Duration | Parallel? |
|-------|-------------|----------|-----------|
| **0. Foundations** | ORM models, ESHM20, EMSC backfill | 1.5 days | ✓ With Phase 1 |
| **1. Ground Truth** | Event labeling, synthetic data, GNSS | 4 days | ✓ With Phase 0, 2 |
| **2. ML Models** | Seismic risk, ETAS, precursor (if GNSS) | 5 days | ✓ With Phase 1 |
| **3. Validation** | CSEP framework, scoring engines | 3 days | After Phase 2 |
| **4. Backend** | API, real-time, parametric designer | 3 days | Parallel to Phase 5 |
| **5. Frontend** | Risk map, events card, damage, aftershock, trigger designer, sidebar | 4 days | Parallel to Phase 4 |
| **Total (sequential critical path)** | | **4 + 5 + 3 = 12 days** | |
| **Total (optimized parallel)** | | **~10–12 days** | |

---

## Critical Decisions Before Starting

**Q1: GNSS Strain Rate Data**
- Can you access EUREF EPN FDSN web service directly?
- If not: defer Phase 1.3 → use catalog-only models (ETAS works without GNSS)

**Q2: Ground Truth Damage Data**
- Can we source actual damage observations for 20+ historical events?
- If only 5–10 events available: train smaller model, use regularization to avoid overfitting

**Q3: Feature Engineering**
- Do we need WorldPop population density, or can we approximate?
- Do we need GEM OpenBuildingMap, or can we use country-level building stock averages?

**Q4: Parametric Pricing**
- Design fee: €50–200K (one-time)
- Annual license: €80–300K
- Settlement event fee: €5–25K per triggered aftershock season
- Acceptable or adjust?

---

## Implementation Order (Recommended)

```
DAY 1 (Mon):   Phase 0 (ORM, ESHM20, EMSC backfill)
DAY 2–3 (Tue–Wed): Phase 1 (ground truth labeling) + early Phase 2 prep
DAY 4–6 (Thu–Fri, Mon): Phase 2 (seismic risk model training)
DAY 7 (Tue):   Phase 2 (ETAS model training)
DAY 8–9 (Wed–Thu): Phase 3 (CSEP validation, scoring engines)
DAY 9–10 (Thu–Fri): Phase 4 (API, parametric designer)
DAY 10–12 (Fri–Mon): Phase 5 (frontend components in parallel with Phase 4)

Final integration & testing: DAY 13–14
```

---

## Success Criteria

- ✓ All EMSC events (1990–present) in DB
- ✓ ESHM20 PGA layer live on Risk Map
- ✓ Seismic risk model achieves >0.75 AUC on test set
- ✓ ETAS model achieves positive information gain vs. Poisson baseline
- ✓ CSEP evaluation complete with confidence intervals
- ✓ Real-time damage assessment (M≥5.0 events trigger within 24h)
- ✓ Aftershock forecasting live post-mainshock
- ✓ Parametric seismic trigger designed & back-tested for Italy/Greece
- ✓ All frontend components integrated + tested
- ✓ Investor document updated with seismic section

