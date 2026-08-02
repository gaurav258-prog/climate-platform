"""Golden-source integrity invariants (consolidated engine review).

These guard the whole canonical_scores → view surface against the classes of defect the review found:
duplicate active rows leaking a double-count, bands that don't bracket their score, and scores out of
range. The physical-risk views must be robust to a stray duplicate active row (they de-duplicate with
DISTINCT ON), so even if an on-demand race re-inserts, no reader double-counts.
"""
from sqlalchemy import text

from core.db.session import get_session


def test_no_duplicate_active_rows_per_key():
    with get_session() as s:
        n = s.execute(text("""
            SELECT COUNT(*) FROM (
                SELECT h3_cell, hazard_type, scenario, time_horizon, COUNT(*) c
                FROM canonical_scores WHERE valid_to IS NULL
                GROUP BY 1,2,3,4 HAVING COUNT(*) > 1) x
        """)).scalar()
    assert n == 0, f"{n} (cell,hazard,scenario,horizon) keys have >1 active canonical row"


def test_physical_risk_views_never_double_count():
    checks = [("v_sc_plot_physical_risk", "plot_id"),
              ("v_portfolio_entity_physical_risk", "entity_id"),
              ("v_bank_asset_physical_risk", "asset_id")]
    with get_session() as s:
        for view, key in checks:
            n = s.execute(text(f"""
                SELECT COUNT(*) FROM (
                    SELECT {key}, hazard_type, scenario, time_horizon, COUNT(*) c
                    FROM {view} GROUP BY 1,2,3,4 HAVING COUNT(*) > 1) x
            """)).scalar()
            assert n == 0, f"{view} double-counts {n} ({key},hazard,scenario,horizon) rows"


def test_all_bands_bracket_their_score_and_scores_in_range():
    with get_session() as s:
        bad_range = s.execute(text("""
            SELECT COUNT(*) FROM canonical_scores WHERE valid_to IS NULL
              AND (risk_score < 0 OR risk_score > 100
                   OR score_ci_lower < 0 OR score_ci_upper > 100)
        """)).scalar()
        bad_bracket = s.execute(text("""
            SELECT COUNT(*) FROM canonical_scores WHERE valid_to IS NULL
              AND score_ci_lower IS NOT NULL
              AND (score_ci_lower > risk_score OR score_ci_upper < risk_score)
        """)).scalar()
    assert bad_range == 0, f"{bad_range} active rows have a score/ci outside [0,100]"
    assert bad_bracket == 0, f"{bad_bracket} active bands do not bracket their score"
