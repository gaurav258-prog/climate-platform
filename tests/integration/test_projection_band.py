"""WS4 projection uncertainty band — honesty invariants on the crop-drought path.

The band is the CMIP6 across-model ±1σ envelope re-scored through the SAME scorer. It must:
  1. be NULL on the current reading and the baseline scenario (no warming applied → no
     fabricated uncertainty — an honest point, not a made-up band);
  2. be present on every projected scenario×horizon that CMIP6 covers;
  3. bracket the central projected score (lo ≤ score ≤ hi).
(Band WIDTH is deliberately NOT asserted monotone in horizon: as scores saturate toward
the 0–100 ceiling the band compresses — an honest artefact of the bounded index, not a bug.)
These run against the olive-drought rows in canonical_scores (scored via
scripts.score_crop_drought). Skips cleanly if that belt hasn't been scored in this env.
"""
import pytest
from sqlalchemy import text

from core.db.session import get_session


def _rows():
    with get_session() as s:
        return s.execute(text("""
            SELECT v.scenario, v.time_horizon,
                   ROUND(AVG(v.physical_risk_score)::numeric, 2) AS score,
                   ROUND(AVG(v.physical_risk_ci_lower)::numeric, 2) AS lo,
                   ROUND(AVG(v.physical_risk_ci_upper)::numeric, 2) AS hi
            FROM v_sc_plot_physical_risk v
            JOIN sc_sourcing_plots p ON p.plot_id = v.plot_id
            JOIN sc_commodities co ON co.commodity_id = p.commodity_id
            WHERE co.name = 'Olive oil' AND v.hazard_type = 'drought'
            GROUP BY v.scenario, v.time_horizon
        """)).mappings().all()


@pytest.fixture(scope="module")
def rows():
    r = _rows()
    if not r:
        pytest.skip("olive drought not scored in this environment")
    return {(x["scenario"], x["time_horizon"]): x for x in r}


def test_current_and_baseline_carry_no_fabricated_band(rows):
    for (scen, horz), r in rows.items():
        if horz == "current" or scen == "baseline":
            assert r["lo"] is None and r["hi"] is None, f"{scen}/{horz} should have no band"


def test_projected_paths_carry_a_band_that_brackets_the_score(rows):
    projected = [((scen, horz), r) for (scen, horz), r in rows.items()
                 if horz != "current" and scen != "baseline"]
    assert projected, "expected projected rows"
    for (scen, horz), r in projected:
        assert r["lo"] is not None and r["hi"] is not None, f"{scen}/{horz} missing band"
        assert r["lo"] <= r["score"] <= r["hi"], f"{scen}/{horz} band does not bracket score"


def test_a_forward_path_shows_real_model_disagreement(rows):
    # at least one covered projection must carry a non-trivial band (else the spread was dropped)
    widths = [r["hi"] - r["lo"] for (scen, horz), r in rows.items()
              if horz != "current" and scen != "baseline" and r["lo"] is not None]
    assert widths and max(widths) > 1.0, "expected a real CMIP6 model-disagreement band somewhere"
