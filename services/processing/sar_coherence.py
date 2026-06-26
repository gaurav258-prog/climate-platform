"""
Co-seismic SAR damage assessment via intensity change detection.

After a M≥5.0 earthquake, this module compares pre-event and post-event
Sentinel-1 GRD backscatter intensity to identify cells with significant
change — a reliable proxy for building collapse and infrastructure damage.

Why intensity change, not interferometric coherence:
  Coherence change (InSAR) is the gold standard and requires SLC (Single Look
  Complex) products. We currently ingest GRD (Ground Range Detected) for flood
  backscatter. Intensity change on GRD gives a usable first damage map within
  24h of the post-event pass; InSAR coherence can be added when SLC ingestion
  is added to the pipeline.

Literature basis:
  Yun et al. (2015) — ARIA damage proxy map, used operationally post-2015 Nepal EQ
  Bignami et al. (2012) — Sentinel-1 building damage, L'Aquila
  Copernicus EMS rapid mapping — standard operational protocol

Algorithm:
  1. Pull pre-event Sentinel-1 backscatter (VV polarisation) from satellite_observations
     for the N days before origin_time (typically last available pass ≤ 6 days prior)
  2. Pull post-event backscatter for first available pass after origin_time
  3. For each H3 cell in the affected area: compute log-ratio = log(post / pre)
  4. Threshold: |log_ratio| > 3σ of background distribution → damage candidate
  5. Apply magnitude-distance attenuation: cells beyond ~2×rupture length get discount
  6. Output: DamageAssessment records per H3 cell with damage_probability 0–1

Database output:
  Writes to `damage_assessments` table (see migration seismic_damage_table.py).
  Each record carries: event_id, h3_cell, damage_probability, confidence, method.
"""
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Maximum radius (km) around epicentre to analyse for damage
MAX_ANALYSIS_RADIUS_KM = 150

# Background σ multiplier for thresholding
SIGMA_THRESHOLD = 3.0

# Sentinel-1 revisit period over Europe (days)
S1_REVISIT_DAYS = 6

# Minimum cells with post-event data to produce a usable map
MIN_CELLS_REQUIRED = 50


@dataclass
class DamageCell:
    h3_cell: str
    damage_probability: float    # 0.0–1.0
    log_ratio: float             # log(post/pre) — signed; large negative = collapse
    confidence: str              # 'high' / 'medium' / 'low'
    pre_backscatter: float       # dB
    post_backscatter: float      # dB
    distance_km: float           # from epicentre


@dataclass
class DamageAssessmentResult:
    event_id: str
    magnitude: float
    origin_time: datetime
    epicentre_lat: float
    epicentre_lon: float
    cells_analysed: int
    cells_damaged: int           # damage_probability > 0.5
    cells_high_confidence: int   # damage_probability > 0.5 AND confidence='high'
    peak_damage_probability: float
    pre_pass_date: Optional[datetime]
    post_pass_date: Optional[datetime]
    method: str                  # 'sar_intensity_change_grd'
    damage_cells: list[DamageCell]


def run_damage_assessment(
    event_id: str,
    magnitude: float,
    origin_time: datetime,
    epicentre_lat: float,
    epicentre_lon: float,
) -> Optional[DamageAssessmentResult]:
    """
    Main entry point. Called by monitor_seismic.py after a M≥5.0 event.
    Returns None if insufficient Sentinel-1 data is available.
    """
    import h3 as h3lib
    from core.db.session import get_session
    from sqlalchemy import text

    logger.info(
        f"[SAR-damage] starting assessment for {event_id} "
        f"M{magnitude} at lat={epicentre_lat:.2f} lon={epicentre_lon:.2f}"
    )

    # Identify H3 cells within analysis radius
    analysis_cells = _cells_within_radius(epicentre_lat, epicentre_lon, MAX_ANALYSIS_RADIUS_KM)
    logger.info(f"[SAR-damage] {len(analysis_cells)} cells in analysis radius")

    # Find pre-event and post-event Sentinel-1 passes in DB
    with get_session() as session:
        pre_pass, pre_data = _fetch_sar_pass(
            session, analysis_cells, before=origin_time
        )
        post_pass, post_data = _fetch_sar_pass(
            session, analysis_cells, after=origin_time
        )

    if pre_data is None or post_data is None:
        logger.warning(
            f"[SAR-damage] insufficient SAR data for {event_id}: "
            f"pre={'found' if pre_data else 'missing'} "
            f"post={'found' if post_data else 'missing'}"
        )
        return None

    if len(post_data) < MIN_CELLS_REQUIRED:
        logger.warning(
            f"[SAR-damage] only {len(post_data)} cells with post-event data, "
            f"need {MIN_CELLS_REQUIRED} — skipping"
        )
        return None

    # Compute damage probability per cell
    damage_cells = _compute_damage_cells(
        pre_data=pre_data,
        post_data=post_data,
        epicentre_lat=epicentre_lat,
        epicentre_lon=epicentre_lon,
        magnitude=magnitude,
    )

    n_damaged = sum(1 for c in damage_cells if c.damage_probability > 0.5)
    n_high = sum(1 for c in damage_cells if c.damage_probability > 0.5 and c.confidence == "high")
    peak = max((c.damage_probability for c in damage_cells), default=0.0)

    result = DamageAssessmentResult(
        event_id=event_id,
        magnitude=magnitude,
        origin_time=origin_time,
        epicentre_lat=epicentre_lat,
        epicentre_lon=epicentre_lon,
        cells_analysed=len(damage_cells),
        cells_damaged=n_damaged,
        cells_high_confidence=n_high,
        peak_damage_probability=peak,
        pre_pass_date=pre_pass,
        post_pass_date=post_pass,
        method="sar_intensity_change_grd",
        damage_cells=damage_cells,
    )

    _write_to_db(result)

    logger.info(
        f"[SAR-damage] {event_id}: {n_damaged} cells damaged "
        f"({n_high} high-confidence), peak={peak:.2f}"
    )
    return result


def _cells_within_radius(lat: float, lon: float, radius_km: float) -> set[str]:
    """Return all H3 res-8 cells within radius_km of the given point."""
    import h3 as h3lib
    centre = h3lib.latlng_to_cell(lat, lon, 8)
    # k-ring radius in H3 grid distance (each ring ~0.86km at res 8)
    k = int(radius_km / 0.86) + 1
    return h3lib.grid_disk(centre, k)


def _fetch_sar_pass(session, cells: set[str], before: datetime = None, after: datetime = None):
    """
    Find the nearest Sentinel-1 pass in satellite_observations.
    Returns (pass_datetime, {h3_cell: raw_value}) or (None, None).
    """
    from sqlalchemy import text

    cells_list = list(cells)
    if not cells_list:
        return None, None

    if before:
        # Most recent pass strictly before origin_time
        row = session.execute(text("""
            SELECT MAX(observed_at) FROM satellite_observations
            WHERE source_provider LIKE 'sentinel1%'
              AND observed_at < :cutoff
              AND h3_cell = ANY(:cells)
        """), {"cutoff": before, "cells": cells_list}).fetchone()
    else:
        # Earliest pass strictly after origin_time
        row = session.execute(text("""
            SELECT MIN(observed_at) FROM satellite_observations
            WHERE source_provider LIKE 'sentinel1%'
              AND observed_at > :cutoff
              AND h3_cell = ANY(:cells)
        """), {"cutoff": after, "cells": cells_list}).fetchone()

    pass_time = row[0] if row else None
    if pass_time is None:
        return None, None

    # Fetch all cells for that pass (within 1h window)
    window_start = pass_time - timedelta(hours=1)
    window_end = pass_time + timedelta(hours=1)
    rows = session.execute(text("""
        SELECT h3_cell, AVG(raw_value) as backscatter
        FROM satellite_observations
        WHERE source_provider LIKE 'sentinel1%'
          AND observed_at BETWEEN :wstart AND :wend
          AND h3_cell = ANY(:cells)
          AND raw_value IS NOT NULL
        GROUP BY h3_cell
    """), {"wstart": window_start, "wend": window_end, "cells": cells_list}).fetchall()

    data = {r[0]: float(r[1]) for r in rows}
    return pass_time, data if data else None


def _compute_damage_cells(
    pre_data: dict,
    post_data: dict,
    epicentre_lat: float,
    epicentre_lon: float,
    magnitude: float,
) -> list[DamageCell]:
    """
    Compute per-cell damage probability from SAR intensity change.

    Log-ratio = log10(sigma_post / sigma_pre) in linear power units.
    Negative log-ratio = decreased backscatter = potential building collapse.
    Very negative values (<-3σ of background) → high damage probability.
    """
    import h3 as h3lib

    common_cells = set(pre_data.keys()) & set(post_data.keys())
    if not common_cells:
        return []

    log_ratios = []
    for cell in common_cells:
        pre_db = pre_data[cell]
        post_db = post_data[cell]
        if pre_db > 0 and post_db > 0:
            # Convert dB to linear power, compute ratio, back to dB
            pre_lin = 10 ** (pre_db / 10)
            post_lin = 10 ** (post_db / 10)
            lr = math.log10(post_lin / pre_lin) * 10  # dB change
            log_ratios.append(lr)

    if not log_ratios:
        return []

    log_ratios_arr = np.array(log_ratios)
    bg_mean = np.median(log_ratios_arr)
    bg_std = np.std(log_ratios_arr)
    if bg_std < 0.01:
        bg_std = 0.01

    # Rupture length approximation (Wells & Coppersmith 1994)
    rupture_length_km = 10 ** (0.69 * magnitude - 3.22)

    damage_cells = []
    cells_list = list(common_cells)
    epicentre_cell = h3lib.latlng_to_cell(epicentre_lat, epicentre_lon, 8)

    for cell in cells_list:
        pre_db = pre_data.get(cell)
        post_db = post_data.get(cell)
        if pre_db is None or post_db is None or pre_db <= 0 or post_db <= 0:
            continue

        pre_lin = 10 ** (pre_db / 10)
        post_lin = 10 ** (post_db / 10)
        lr = math.log10(post_lin / pre_lin) * 10

        # Distance from epicentre (H3 grid distance × ~0.86km)
        grid_dist = h3lib.grid_distance(cell, epicentre_cell)
        dist_km = grid_dist * 0.86

        # Normalised deviation from background
        z_score = (lr - bg_mean) / bg_std

        # Large negative z-score = anomalous decrease = potential damage
        raw_prob = _z_to_prob(z_score)

        # Distance attenuation: GMPEs show shaking falls off ~1/r beyond rupture length
        attenuation = max(0.1, 1.0 - max(0.0, dist_km - rupture_length_km) / (3 * rupture_length_km))
        damage_prob = raw_prob * attenuation

        if abs(z_score) >= SIGMA_THRESHOLD and dist_km <= rupture_length_km * 2:
            confidence = "high"
        elif abs(z_score) >= 2.0:
            confidence = "medium"
        else:
            confidence = "low"

        damage_cells.append(DamageCell(
            h3_cell=cell,
            damage_probability=min(1.0, damage_prob),
            log_ratio=lr,
            confidence=confidence,
            pre_backscatter=pre_db,
            post_backscatter=post_db,
            distance_km=dist_km,
        ))

    return damage_cells


def _z_to_prob(z_score: float) -> float:
    """
    Convert z-score to damage probability.
    Only large NEGATIVE deviations (decreased backscatter) indicate damage.
    Large positive deviations (increased backscatter) are also scored — can indicate
    liquefaction, landslide, or rubble scattering (also damaging outcomes).
    """
    abs_z = abs(z_score)
    if abs_z < 1.5:
        return 0.0
    elif abs_z < 2.0:
        return 0.10
    elif abs_z < 3.0:
        return 0.35
    elif abs_z < 4.0:
        return 0.65
    elif abs_z < 5.0:
        return 0.82
    else:
        return 0.95


def _write_to_db(result: DamageAssessmentResult):
    """Persist damage assessment to database."""
    from core.db.session import get_session
    from sqlalchemy import text

    records = [
        {
            "event_id": result.event_id,
            "h3_cell": c.h3_cell,
            "damage_probability": c.damage_probability,
            "log_ratio_db": c.log_ratio,
            "confidence": c.confidence,
            "distance_km": c.distance_km,
            "method": result.method,
            "pre_pass_time": result.pre_pass_date.isoformat() if result.pre_pass_date else None,
            "post_pass_time": result.post_pass_date.isoformat() if result.post_pass_date else None,
            "assessed_at": datetime.now(timezone.utc).isoformat(),
        }
        for c in result.damage_cells
        if c.damage_probability > 0.05  # only write cells with meaningful signal
    ]

    if not records:
        return

    with get_session() as session:
        session.execute(text("""
            INSERT INTO damage_assessments
                (event_id, h3_cell, damage_probability, log_ratio_db,
                 confidence, distance_km, method,
                 pre_pass_time, post_pass_time, assessed_at)
            VALUES
                (:event_id, :h3_cell, :damage_probability, :log_ratio_db,
                 :confidence, :distance_km, :method,
                 :pre_pass_time, :post_pass_time, :assessed_at)
            ON CONFLICT (event_id, h3_cell) DO UPDATE
              SET damage_probability = EXCLUDED.damage_probability,
                  confidence = EXCLUDED.confidence,
                  assessed_at = EXCLUDED.assessed_at
        """), records)

    logger.info(f"[SAR-damage] wrote {len(records)} damage cells for {result.event_id}")
