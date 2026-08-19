"""The validation record's model figure must come from the ENGINE, not from the observation.

THE REGRESSION THIS GUARDS (real, 2026-07-16, found 2026-07-17). cocoa_refit_20260716 wrote
    observed_prod_shock_pct = -8.88,
    model_prod_shock_pct    = -8.88,
in a single UPDATE, and the skill_note beside it then advertised "INDEPENDENT CONFIRMATION ...
two unrelated sources converging". Two sources cannot converge when one is assigned from the
other. The exact match was not evidence of skill; it was evidence of a copy.

A backtest is worth exactly nothing if the model's answer is defined as the right answer, and
this is the single easiest way for that to creep back in: someone re-runs a fit, pastes the
observed figure into both columns, and the Trust page reports a perfect score forever.

Requires PostgreSQL.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.intelligence.supply_cogs import project_org_supply


@pytest.mark.integration
def test_model_prod_shock_is_not_copied_from_the_observation():
    """No passing row may have model == observed to the last digit. A real model reproduces a
    real measurement with a real, non-zero error."""
    with get_session() as s:
        rows = s.execute(text("""
            SELECT event, origin, model_prod_shock_pct, observed_prod_shock_pct
            FROM sc_model_validation
            WHERE passed AND model_prod_shock_pct IS NOT NULL
              AND observed_prod_shock_pct IS NOT NULL
        """)).mappings().all()
    assert rows, "no passing rows with both figures — the guard would vacuously pass"
    for r in rows:
        assert float(r["model_prod_shock_pct"]) != float(r["observed_prod_shock_pct"]), (
            f"{r['event']}/{r['origin']}: model figure is identical to the observed figure. "
            "That is a copy, not a backtest."
        )


@pytest.mark.integration
def test_cocoa_recorded_claim_matches_what_the_engine_actually_produces():
    """The recorded model figure must be the engine's live output. If someone re-fits cocoa and
    forgets to update the record, the Trust page would advertise a number the product no longer
    computes — so tie the record to the engine, not to a note."""
    with get_session() as s:
        org = s.execute(text(
            "SELECT org_id FROM organizations WHERE name ILIKE '%Terra%' LIMIT 1"
        )).scalar()
        if org is None:
            pytest.skip("no agriculture demo org seeded")
        live = project_org_supply(s, org)
        cocoa = next((c for c in live.commodities if c.commodity == "Cocoa"), None)
        if cocoa is None or cocoa.global_shock_pct is None:
            pytest.skip("cocoa not scored in this database")

        recorded = s.execute(text("""
            SELECT model_prod_shock_pct FROM sc_model_validation
            WHERE event = 'Cocoa 2023/24' AND passed LIMIT 1
        """)).scalar()

    # the column's convention is signed (a contraction is negative); the engine reports magnitude
    assert abs(float(recorded)) == pytest.approx(cocoa.global_shock_pct, abs=0.05), (
        f"recorded claim {recorded} != engine output {cocoa.global_shock_pct}"
    )


@pytest.mark.integration
def test_the_claim_still_beats_the_measurement_it_is_tested_against():
    """The point of the fix is not that the numbers differ — it is that the claim survives on
    its own. 8.92 modelled vs FAOSTAT's 8.88 measured is a 0.45% error between two figures with
    no shared input."""
    with get_session() as s:
        r = s.execute(text("""
            SELECT model_prod_shock_pct AS m, observed_prod_shock_pct AS o
            FROM sc_model_validation WHERE event = 'Cocoa 2023/24' AND passed LIMIT 1
        """)).mappings().first()
    err = abs(abs(float(r["m"])) - abs(float(r["o"]))) / abs(float(r["o"])) * 100
    assert err < 5.0, f"cocoa's volume claim no longer reproduces FAO ({err:.1f}% error)"
