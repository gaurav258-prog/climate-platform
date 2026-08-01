"""Calibration drift / re-validation control (audit T12).

A published crop calibration is fit against a training window ending in `baseline_to`. Validation was
one-time: nothing flagged that, as crop-years accumulate past that window, the fit has never been
re-checked against them — so a relationship that has drifted would go unnoticed. This surfaces the
control. It does NOT silently retire a calibration (that would be its own dishonesty); it flags which
published calibrations are due for re-validation so a human re-fits and re-checks them.

The horizon (a published calibration re-validates at least this often) is an honesty constant, not a
per-org knob — the same reasoning as the r² publish floor.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

REVALIDATION_HORIZON_YEARS = 3


def overdue_calibrations(session: Session, as_of_year: Optional[int] = None) -> list[dict]:
    """Published (ranged/backtested) calibrations whose training window ends >= the horizon behind the
    reporting year — i.e. enough new crop-years exist that they should be re-validated. Most-stale first."""
    yr = as_of_year or date.today().year
    rows = session.execute(text("""
        SELECT cal.commodity_id, cm.name AS commodity, cal.origin, cal.hazard_driver,
               cal.baseline_to, cal.calibration_tier
        FROM   v_sc_commodity_calibration cal
        JOIN   sc_commodities cm ON cm.commodity_id = cal.commodity_id
        WHERE  cal.calibration_tier IN ('ranged', 'backtested')
    """)).mappings().all()

    overdue = []
    for r in rows:
        bt = r["baseline_to"]
        if bt is None:
            continue
        behind = yr - int(bt)
        if behind >= REVALIDATION_HORIZON_YEARS:
            overdue.append({
                "commodity": r["commodity"], "origin": r["origin"],
                "hazard_driver": r["hazard_driver"], "tier": r["calibration_tier"],
                "trained_through": int(bt), "years_behind": behind,
            })
    return sorted(overdue, key=lambda x: -x["years_behind"])


def revalidation_status(session: Session, as_of_year: Optional[int] = None) -> dict:
    """Compact status for a readiness check: how many published calibrations are due for re-validation."""
    overdue = overdue_calibrations(session, as_of_year)
    return {
        "horizon_years": REVALIDATION_HORIZON_YEARS,
        "as_of_year": as_of_year or date.today().year,
        "overdue_count": len(overdue),
        "overdue": overdue,
    }
