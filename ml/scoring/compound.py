"""
Cross-hazard compound event detector.

A compound event is when two or more hazard types are simultaneously elevated
in the same H3 cell for a sustained period. This is a major blind spot in the
industry — existing platforms score hazards independently and miss co-occurring
risks that amplify each other:

  Drought  + Wildfire  → fuel moisture at critical low + active fire = catastrophic spread
  Heat     + Drought   → crop failure + infrastructure stress (same cells)
  Flood    + Heat      → post-flood heatwave amplifies public health impact

No competitor detects this in real-time because no competitor has a unified
canonical score store across hazard types. We do.

Usage:
    from ml.scoring.compound import CompoundDetector
    detector = CompoundDetector(session)
    flags = detector.detect(target_date, scored_cells_df)
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Threshold above which a hazard score is considered "elevated"
COMPOUND_SCORE_THRESHOLD = 60.0   # score ≥ 60 (HIGH or above)

# Minimum consecutive days both hazards must be elevated
COMPOUND_MIN_DAYS = 3

# Hazard pairs that constitute meaningful compound events
COMPOUND_PAIRS = [
    ("wildfire", "flood"),      # drought precursor → wildfire, then rain → flash flood
    ("heat_acute", "wildfire"), # extreme heat dries fuel, elevates wildfire
    ("heat_acute", "flood"),    # heat + atmospheric instability → intense convective floods
    ("heat_acute", "drought"),  # sustained heat worsens drought
]


class CompoundDetector:
    """
    Detects compound events by cross-referencing canonical_scores across hazard types.

    For each H3 cell scored today, looks back COMPOUND_MIN_DAYS days to check
    whether a second hazard has also been elevated for the same period.
    """

    def __init__(self, session: Session):
        self._session = session

    def detect(self, target_date: date, scored_df: pd.DataFrame,
               hazard_type: str) -> pd.Series:
        """
        For each cell in scored_df, return True if a compound event is active.

        scored_df must have columns: h3_cell, score
        hazard_type: the hazard being scored in this run (e.g. 'flood')

        Returns a boolean Series indexed same as scored_df.
        """
        elevated_today = set(
            scored_df.loc[scored_df["score"] >= COMPOUND_SCORE_THRESHOLD, "h3_cell"]
        )

        if not elevated_today:
            return pd.Series(False, index=scored_df.index)

        compound_cells = set()

        for pair in COMPOUND_PAIRS:
            if hazard_type not in pair:
                continue
            other_hazard = pair[0] if pair[1] == hazard_type else pair[1]

            sustained = self._cells_elevated_for_days(
                cells=elevated_today,
                hazard_type=other_hazard,
                as_of=target_date,
                n_days=COMPOUND_MIN_DAYS,
            )
            if sustained:
                logger.info(
                    f"[Compound] {hazard_type}+{other_hazard}: "
                    f"{len(sustained)} cells elevated ≥{COMPOUND_MIN_DAYS}d"
                )
                compound_cells.update(sustained)

        return scored_df["h3_cell"].isin(compound_cells)

    def _cells_elevated_for_days(
        self,
        cells: set[str],
        hazard_type: str,
        as_of: date,
        n_days: int,
    ) -> set[str]:
        """
        Return the subset of `cells` where `hazard_type` risk_score ≥ threshold
        on EVERY one of the last `n_days` days (including as_of).
        """
        window_start = as_of - timedelta(days=n_days - 1)

        rows = self._session.execute(text("""
            SELECT   h3_cell,
                     COUNT(DISTINCT scored_at::date) AS days_elevated
            FROM     canonical_scores
            WHERE    h3_cell     = ANY(:cells)
            AND      hazard_type = :hazard
            AND      risk_score  >= :threshold
            AND      scored_at  >= :window_start
            AND      scored_at  <= :as_of
            AND      valid_to    IS NULL
            GROUP BY h3_cell
            HAVING   COUNT(DISTINCT scored_at::date) >= :min_days
        """), {
            "cells":        list(cells),
            "hazard":       hazard_type,
            "threshold":    COMPOUND_SCORE_THRESHOLD,
            "window_start": str(window_start),
            "as_of":        str(as_of),
            "min_days":     n_days,
        }).fetchall()

        return {row[0] for row in rows}


def summarise_compound_events(session: Session, target_date: date) -> list[dict]:
    """
    Return a summary of active compound events for the dashboard / alert service.
    Queries canonical_scores for today's scores across all hazard types.
    """
    rows = session.execute(text("""
        SELECT   h3_cell,
                 array_agg(DISTINCT hazard_type ORDER BY hazard_type) AS hazards,
                 AVG(risk_score)                                       AS avg_score
        FROM     canonical_scores
        WHERE    scored_at::date = :target_date
        AND      risk_score     >= :threshold
        AND      valid_to        IS NULL
        GROUP BY h3_cell
        HAVING   COUNT(DISTINCT hazard_type) >= 2
        ORDER BY avg_score DESC
        LIMIT    1000
    """), {
        "target_date": str(target_date),
        "threshold":   COMPOUND_SCORE_THRESHOLD,
    }).fetchall()

    return [
        {
            "h3_cell":    row[0],
            "hazards":    row[1],
            "avg_score":  float(row[2]),
        }
        for row in rows
    ]
