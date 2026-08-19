"""The 'ranged' publish tier must be earned on OUT-OF-SAMPLE r² (r2_oos), not in-sample r².

Audit finding F2: the tier view used to gate on `sc_commodity_fit.r2` — the in-sample r² the fitting
code itself labels "the optimistic number" — while the honest leave-one-out `r2_oos` only fed the
advisory Confidence Grade. A crop could publish a € band on an optimistic 0.42 whose honest OOS skill
was 0.24. The gate now keys on r2_oos (migration ranged_gate_oos_20260731). These tests hold that line.
Requires PostgreSQL.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.intelligence.supply_cogs import RANGED_PUBLISH_FLOOR


@pytest.mark.integration
def test_every_ranged_crop_clears_the_out_of_sample_floor():
    """No commodity×origin may be 'ranged' unless its fit's out-of-sample r² ≥ the publish floor."""
    with get_session() as s:
        rows = s.execute(text("""
            SELECT co.name AS commodity, cal.origin, f.r2, f.r2_oos
            FROM v_sc_commodity_calibration cal
            JOIN sc_commodities co ON co.commodity_id = cal.commodity_id
            JOIN sc_commodity_fit f
              ON f.commodity_id = cal.commodity_id
             AND f.origin::text = cal.origin::text
             AND f.hazard_driver::text = cal.hazard_driver::text
            WHERE cal.calibration_tier = 'ranged'
        """)).mappings().all()
    assert rows, "no ranged crops found — seed/fixture missing"
    for r in rows:
        assert r["r2_oos"] is not None and float(r["r2_oos"]) >= RANGED_PUBLISH_FLOOR, (
            f"{r['commodity']}/{r['origin']} publishes as 'ranged' but its out-of-sample "
            f"r²={r['r2_oos']} is below the {RANGED_PUBLISH_FLOOR} floor (in-sample r²={r['r2']}). "
            f"The gate must be on r2_oos."
        )


@pytest.mark.integration
def test_in_sample_pass_but_oos_fail_is_held_not_ranged():
    """A fit that clears the floor in-sample but fails out-of-sample must NOT be 'ranged'."""
    with get_session() as s:
        leaked = s.execute(text("""
            SELECT co.name AS commodity, cal.origin, f.r2, f.r2_oos
            FROM v_sc_commodity_calibration cal
            JOIN sc_commodities co ON co.commodity_id = cal.commodity_id
            JOIN sc_commodity_fit f
              ON f.commodity_id = cal.commodity_id
             AND f.origin::text = cal.origin::text
             AND f.hazard_driver::text = cal.hazard_driver::text
            WHERE cal.calibration_tier = 'ranged'
              AND f.r2 >= :floor
              AND (f.r2_oos IS NULL OR f.r2_oos < :floor)
        """), {"floor": RANGED_PUBLISH_FLOOR}).mappings().all()
    assert not leaked, (
        "these publish 'ranged' on optimistic in-sample r² while failing out-of-sample: "
        + ", ".join(f"{r['commodity']}/{r['origin']} (r2={r['r2']}, r2_oos={r['r2_oos']})" for r in leaked)
    )
