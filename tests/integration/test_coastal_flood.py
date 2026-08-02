"""WS4d — sea-level-rise coastal-flood hazard: scored only for coastal cells, with an honest band.

coastal_flood is a DISTINCT hazard (sea-driven) from the rain-driven flood, scored from each cell's
elevation + distance-to-coast against AR6 sea-level rise. Invariants against the live golden source:
  1. it exists only on coastal cells (never on an inland asset — the hazard is absent there);
  2. baseline + current carry no SLR band (today's exposure held flat); forward SSP carries a band
     that brackets the central score;
  3. it coexists with the ordinary flood hazard on the same cell (two mechanisms, not one).
Skips cleanly if coastal_flood hasn't been scored in this environment.
"""
import pytest
from sqlalchemy import text

from core.db.session import get_session


def _rows():
    with get_session() as s:
        return s.execute(text("""
            SELECT scenario, time_horizon,
                   ROUND(risk_score::numeric, 2) AS score,
                   ROUND(score_ci_lower::numeric, 2) AS lo, ROUND(score_ci_upper::numeric, 2) AS hi
            FROM canonical_scores
            WHERE hazard_type = 'coastal_flood' AND valid_to IS NULL
              AND COALESCE(score_lane,'standing') = 'standing'
        """)).mappings().all()


@pytest.fixture(scope="module")
def rows():
    r = _rows()
    if not r:
        pytest.skip("coastal_flood not scored in this environment")
    return r


def test_only_scored_on_coastal_cells(rows):
    with get_session() as s:
        bad = s.execute(text("""
            SELECT COUNT(*) FROM canonical_scores cs
            LEFT JOIN coastal_exposure ce ON ce.h3_cell = cs.h3_cell
            WHERE cs.hazard_type = 'coastal_flood' AND cs.valid_to IS NULL
              AND (ce.is_coastal IS DISTINCT FROM true)
        """)).scalar()
    assert bad == 0, "coastal_flood must only exist on coastal cells"


def test_baseline_current_flat_forward_banded(rows):
    for r in rows:
        if r["scenario"] == "baseline" or r["time_horizon"] == "current":
            assert r["lo"] is None and r["hi"] is None, f"{r['scenario']}/{r['time_horizon']} should carry no SLR band"
    fwd = [r for r in rows if r["scenario"] != "baseline" and r["time_horizon"] != "current" and r["lo"] is not None]
    assert fwd, "expected forward SLR bands"
    for r in fwd:
        assert r["lo"] <= r["score"] <= r["hi"], "SLR band must bracket the central score"


def test_coexists_with_ordinary_flood(rows):
    # coastal_flood and flood are distinct mechanisms — a coastal cell can carry BOTH
    with get_session() as s:
        both = s.execute(text("""
            SELECT COUNT(DISTINCT cf.h3_cell) FROM canonical_scores cf
            JOIN canonical_scores f ON f.h3_cell = cf.h3_cell AND f.hazard_type = 'flood' AND f.valid_to IS NULL
            WHERE cf.hazard_type = 'coastal_flood' AND cf.valid_to IS NULL
        """)).scalar()
    assert both > 0, "expected at least one cell carrying both flood and coastal_flood"
