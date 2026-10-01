"""Test fixture: an institution's COMPLETE stated method for a financial year (E69), written straight into the store the
engines read (provided values, family 'method', attested) — so a test that files a money report exercises the figures,
not the gap. The numbers are test values for the mechanics only, stated through the 'any' members; they are nobody's
method. A test of the stated lane itself goes through the API with four eyes (test_money_method_lane.py)."""
from __future__ import annotations

from sqlalchemy import text

from services.money.params import members

_BANDS = {"L": 0, "M": 1, "H": 2, "VH": 3}
TEST_METHOD = {
    ("method.at_risk_level", None): 50,
    **{("method.valuation_haircut", f"any/{b}"): v for b, v in zip(_BANDS, (0.0, 0.05, 0.15, 0.30))},
    **{("method.damage_ratio", f"any/{b}"): v for b, v in zip(_BANDS, (0.02, 0.10, 0.30, 0.50))},
    **{("method.annual_event_probability", f"any/{b}"): v for b, v in zip(_BANDS, (0.002, 0.005, 0.01, 0.02))},
    **{("method.resilience_capex_share", b): v for b, v in zip(_BANDS, (0.003, 0.01, 0.025, 0.04))},
    ("method.adaptation_effectiveness", "any"): 0.3,
    ("method.var_relative_uncertainty", None): 0.4, ("method.transition_var_relative_uncertainty", None): 0.5,
    ("method.expense_ratio", None): 0.25, ("method.profit_margin", None): 0.05,
    ("method.frequency_review_tolerance", None): 0.5,
    ("method.runway_materiality", None): 0.05,
    **{("method.bi_downtime_share", f"any/{b}"): v for b, v in zip(_BANDS, (0.0, 0.01, 0.03, 0.06))},
    **{("method.stranded_share", m): 0.02 for m in members("division_scenario_horizon") if m.startswith("any@")},
    **{("method.carbon_price", m): 100.0 for m in members("scenario_horizon")},
    **{("method.brown_discount", g): v for g, v in zip("ABCDEFG", (0, 0, 0, 0, 0.05, 0.10, 0.15))},
    **{("method.retrofit_capex_share", g): v for g, v in zip("ABCDEFG", (0, 0, 0, 0, 0.04, 0.08, 0.12))},
}


def set_aside_method(session, org_id: str, period_end) -> None:
    """Inside the rolled-back transaction: the organisation's method for that year as the database holds it (e.g. the
    demo seed, E82) is set aside, so a test reads only the method it states itself (E85)."""
    session.execute(text("""UPDATE provided_datapoint SET status = 'superseded' WHERE org_id = CAST(:o AS uuid)
                            AND framework = 'method' AND reporting_period_end = CAST(:pe AS date) AND status <> 'superseded'"""),
                    {"o": org_id, "pe": str(period_end)[:10]})


def state_method(session, org_id: str, period_end, values: dict | None = None) -> None:
    """State `values` (default TEST_METHOD) as the organisation's attested method for the year ending period_end — the
    whole method: whatever the database already held for that year is set aside first."""
    set_aside_method(session, org_id, period_end)
    for (key, member), v in (values or TEST_METHOD).items():
        session.execute(text("""
            INSERT INTO provided_datapoint (org_id, framework, datapoint_key, value_num, unit, source, status,
                                            reporting_period_end, breakdown_member, decided_at)
            VALUES (CAST(:o AS uuid), 'method', :k, :v, NULL, 'client', 'attested', CAST(:pe AS date), :m, now())
        """), {"o": org_id, "k": key, "v": v, "pe": str(period_end)[:10], "m": member})
