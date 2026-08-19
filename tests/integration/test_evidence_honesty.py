"""Evidence-concentration honesty invariants (audit T11).

Two guarantees that keep a thin-evidence euro honest:
  1. A validation that FAILED (passed=false) never promotes a crop to the published 'backtested' tier —
     a failed backtest cannot publish a euro (Coffee-BR drought, Coffee-GT volcanic, Coffee-PR storm live).
  2. A single-event backtested crop (Cocoa) carries the single-event caveat in its Confidence Grade —
     the thin evidence is disclosed, never hidden behind a clean letter.

The genuinely independent challenger MODEL is a disclosed roadmap gap (docs/CALC_ENGINE_AUDIT.md T11),
not faked here. Requires PostgreSQL.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from ml.confidence_grade import grade


@pytest.mark.integration
def test_failed_validation_never_publishes_backtested():
    with get_session() as s:
        # any commodity·origin·hazard whose validations are ALL passed=false must not be 'backtested'
        rows = s.execute(text("""
            SELECT v.commodity_id, v.origin, v.hazard
            FROM   sc_model_validation v
            GROUP  BY v.commodity_id, v.origin, v.hazard
            HAVING bool_or(v.passed) = false
        """)).mappings().all()
        assert rows, "expected at least one all-failed validation group live (Coffee-BR/GT/PR)"
        for r in rows:
            tier = s.execute(text("""
                SELECT calibration_tier FROM v_sc_commodity_calibration
                WHERE commodity_id=:c AND origin=:o AND hazard_driver=:h
            """), {"c": r["commodity_id"], "o": r["origin"], "h": r["hazard"]}).scalar()
            assert tier != "backtested", (
                f"a failed validation published as backtested: {r['origin']}/{r['hazard']}")


def test_single_event_backtest_discloses_the_caveat():
    # Cocoa's shape: one event reproduced tightly. Grade must still disclose the single-event weakness.
    g = grade(tier="backtested", reproduction_err_pct=0.1, n_events=1)
    depth = next(c for c in g.checks if c["key"] == "evidence_depth")
    hrange = next(c for c in g.checks if c["key"] == "honest_range")
    assert depth["points"] <= 1, "single-event evidence must not score Strong on depth"
    assert "single-event" in hrange["detail"], "single-event uncertainty must be disclosed in the grade"
