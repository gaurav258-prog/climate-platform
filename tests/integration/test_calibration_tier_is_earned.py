"""The calibration tier must be EARNED, not typed.

'backtested' is the strongest claim the product makes — it is what lets a euro reach a
customer. It used to be a free-text column on sc_commodity_calibration that anyone (including
the seed that created it) could set by hand. The rule "no € without a backtest" was a
convention, enforced by nobody.

Now the tier is DERIVED from sc_model_validation: backtested iff a validation row exists that
PASSED, on the same hazard the coefficient drives. These tests hold that line.
Requires PostgreSQL.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.intelligence.supply_cogs import get_calibrations


@pytest.mark.integration
def test_tier_column_cannot_be_typed_it_does_not_exist():
    """There is no hand-settable calibration_tier column to write 'backtested' into."""
    with get_session() as s:
        cols = s.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'sc_commodity_calibration'
        """)).scalars().all()
    assert "calibration_tier" not in cols, \
        "calibration_tier is settable by hand again — the tier must be derived from evidence"


@pytest.mark.integration
def test_backtested_requires_a_passing_validation_row():
    """Every origin the engine calls 'backtested' must have passing evidence behind it."""
    with get_session() as s:
        cal = get_calibrations(s)
        rows = s.execute(text("""
            SELECT co.name AS commodity, v.origin, v.hazard
            FROM sc_model_validation v JOIN sc_commodities co ON co.commodity_id = v.commodity_id
            WHERE v.passed
        """)).mappings().all()
    evidence = {(r["commodity"], r["origin"], r["hazard"]) for r in rows}

    for commodity, origins in cal.items():
        for origin, p in origins.items():
            if p["calibration_tier"] == "backtested":
                assert (commodity, origin, p["hazard_driver"]) in evidence, (
                    f"{commodity}/{origin} claims 'backtested' with no passing validation "
                    f"on its driver hazard {p['hazard_driver']}"
                )


@pytest.mark.integration
def test_order_of_magnitude_checks_do_not_earn_backtested():
    """Guatemala volcanic + Puerto Rico storm were order-of-magnitude checks with no clean
    origin-specific anchor (passed=false). They must NOT publish a €."""
    with get_session() as s:
        cal = get_calibrations(s)
    coffee = cal.get("Coffee", {})
    for origin in ("GT", "PR"):
        if origin in coffee:
            assert coffee[origin]["calibration_tier"] == "indicative", \
                f"Coffee/{origin} must stay indicative — its check never reproduced the event"


@pytest.mark.integration
def test_failing_the_validation_demotes_the_tier():
    """Flip the evidence to failed and the tier must follow — the claim tracks the proof."""
    with get_session() as s:
        before = get_calibrations(s)["Cocoa"]["CI"]["calibration_tier"]
        assert before == "backtested"
        s.execute(text("""
            UPDATE sc_model_validation SET passed = false
            WHERE commodity_id = (SELECT commodity_id FROM sc_commodities WHERE name='Cocoa')
              AND origin = 'CI'
        """))
        try:
            demoted = get_calibrations(s)["Cocoa"]["CI"]["calibration_tier"]
            assert demoted == "indicative", "tier did not follow the evidence"
        finally:
            s.execute(text("""
                UPDATE sc_model_validation SET passed = true
                WHERE commodity_id = (SELECT commodity_id FROM sc_commodities WHERE name='Cocoa')
                  AND origin = 'CI'
            """))

    with get_session() as s:
        assert get_calibrations(s)["Cocoa"]["CI"]["calibration_tier"] == "backtested"


@pytest.mark.integration
def test_validation_on_a_different_hazard_does_not_count():
    """A backtest proves a coefficient against ONE hazard. Evidence on some other hazard must
    not license the driver the engine actually uses."""
    with get_session() as s:
        rows = s.execute(text("""
            SELECT co.name AS commodity, c.origin, c.hazard_driver, c.calibration_tier
            FROM v_sc_commodity_calibration c JOIN sc_commodities co ON co.commodity_id = c.commodity_id
            WHERE c.calibration_tier = 'backtested'
        """)).mappings().all()
        for r in rows:
            match = s.execute(text("""
                SELECT count(*) FROM sc_model_validation v
                JOIN sc_commodities co ON co.commodity_id = v.commodity_id
                WHERE co.name = :c AND v.origin = :o AND v.passed AND v.hazard = :h
            """), {"c": r["commodity"], "o": r["origin"], "h": r["hazard_driver"]}).scalar()
            assert match > 0, f"{r['commodity']}/{r['origin']} backtested on the wrong hazard"
