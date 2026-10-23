"""Regional crop calibrations end to end in the database (rolled back): a regional run publishes under its region code
and never over its country's fit; a held regional run is never proposed; the tier view needs a damage response (E327);
the regional coverage says what each region publishes."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from services.calibration import coverage, publish, specs

pytestmark = pytest.mark.integration


def _regional_run(s, commodity: str, region: str, *, r2_oos: float, slope: float, passes: bool) -> tuple[str, str]:
    """A regional recipe and one recorded run with stated figures (no weather read — the publication path is tested)."""
    s.execute(text("UPDATE crop_calibration_specs SET retired_at = now(), retired_reason = 'test' WHERE commodity = :c "
                   "AND yield_region = :g AND retired_at IS NULL"), {"c": commodity, "g": region})
    sid = specs.create(s, commodity=commodity, origin=region[:2], yield_source="EUROSTAT apro_cpshr", yield_region=region,
                       driver="drought", weather_kind="crop_area", weather_key="mapspam2020:BARL",
                       season_months=[1, 2, 3, 4, 5, 6], season_prev_months=[11, 12], allow_cycle=False,
                       basis="test regional recipe", protocol="crop-calib-reg-v1")
    rid = s.execute(text("""
        INSERT INTO crop_calibration_runs (spec_id, inputs, outcome, n_years, baseline_from, baseline_to, slope, intercept,
               r2, r2_oos, rmse, score_mean, score_sxx, band_cov68, downside_pass, upside, upside_pass)
        VALUES (CAST(:s AS uuid), CAST(:i AS jsonb), 'fitted', 16, 2003, 2021, :b, 40, 0.6, :r, 8, 50, 9000, 0.7, :p,
                CAST(:u AS jsonb), false) RETURNING run_id::text"""),
        {"s": sid, "i": json.dumps({"test": True}), "b": slope, "r": r2_oos, "p": passes,
         "u": json.dumps({"pass": False, "failed": []})}).scalar()
    return sid, rid


def _country_fit(s, commodity: str, origin: str):
    return s.execute(text("""SELECT f.run_id::text, CAST(f.r2_oos AS FLOAT) FROM sc_commodity_fit f JOIN sc_commodities c
                             USING (commodity_id) WHERE c.name = :c AND f.origin = :o AND f.hazard_driver = 'drought'"""),
                     {"c": commodity, "o": origin}).first()


def test_a_regional_run_publishes_under_its_region_never_over_its_country(session_rolled_back):
    s = session_rolled_back
    before = _country_fit(s, "Barley", "ES")
    _sid, rid = _regional_run(s, "Barley", "ES24", r2_oos=0.63, slope=-0.9, passes=True)
    assert publish.changes(s, rid)["first"] is True
    s.execute(text("""UPDATE approval_policy SET human_approvers = 1 WHERE action_key = 'calibration.publish'
                      AND org_id = '99999999-9999-4999-8999-999999999999'"""))
    assert publish.propose(s, [rid], "test regional publication")["runs"] == 1
    checker = s.execute(text("SELECT user_id::text FROM users WHERE email = 'ops@tellumen.io'")).scalar()
    assert publish.apply_decision(s, {"run_ids": [rid]}, "approved", checker, "test") == {"status": "published", "runs": 1}
    assert _country_fit(s, "Barley", "ES24")[0] == rid
    assert _country_fit(s, "Barley", "ES") == before                       # the country's own fit untouched
    tier = s.execute(text("""SELECT v.calibration_tier FROM v_sc_commodity_calibration v JOIN sc_commodities c
                             USING (commodity_id) WHERE c.name = 'Barley' AND v.origin = 'ES24'""")).scalar()
    assert tier == "ranged"
    s.execute(text("""INSERT INTO crop_calibration_coverage (commodity, origin, region, area_ha, area_share, status, spec_id)
                      VALUES ('Barley', 'ES', 'ES24', 467000, 0.176, 'recipe', CAST(:s AS uuid))
                      ON CONFLICT (commodity, origin, region) DO UPDATE SET status = 'recipe', reason = NULL,
                          spec_id = EXCLUDED.spec_id"""), {"s": _sid})
    row = next(r for r in coverage.regional(s, "Barley")["rows"] if r["region"] == "ES24")
    assert row["category"] == "loss" and row["name"] == "Aragón" and row["r2_oos"] == 0.63


def test_every_protocol_id_fits_the_columns_a_publication_writes(session_rolled_back):
    """A run's protocol is written to sc_commodity_calibration.impact_version and sc_commodity_fit.fit_version: every
    protocol id the reference states must fit both (the regional id did not, and its first publication failed)."""
    from services.calibration.gates import protocol
    s = session_rolled_back
    width = dict(s.execute(text("""SELECT table_name, character_maximum_length FROM information_schema.columns
        WHERE (table_name, column_name) IN (('sc_commodity_calibration', 'impact_version'),
                                            ('sc_commodity_fit', 'fit_version'))""")).all())
    for pid in (protocol()["protocol"], protocol()["regional"]["protocol"]):
        assert len(pid) <= min(width.values()), pid


def test_a_held_regional_run_is_never_proposed(session_rolled_back):
    s = session_rolled_back
    _sid, rid = _regional_run(s, "Barley", "ES41", r2_oos=0.37, slope=-0.85, passes=False)
    assert publish.changes(s, rid) is None
    assert publish.propose(s, [rid], "test") is None


def test_e327_the_tier_view_needs_a_damage_response(session_rolled_back):
    """A stored fit above the floor whose slope says more drought, more yield derives no 'ranged' tier."""
    s = session_rolled_back
    _sid, rid = _regional_run(s, "Sugar beet", "ES41", r2_oos=0.43, slope=0.3, passes=False)
    cid = s.execute(text("SELECT commodity_id FROM sc_commodities WHERE name = 'Sugar beet'")).scalar()
    s.execute(text("""INSERT INTO sc_commodity_fit (commodity_id, origin, hazard_driver, n_years, slope, intercept, r2, rmse,
                          score_mean, score_sxx, r2_oos) VALUES (:c, 'ES41', 'drought', 16, 0.3, -10, 0.57, 8, 50, 9000, 0.43)
                      ON CONFLICT (commodity_id, origin, hazard_driver) DO UPDATE SET slope = 0.3, r2_oos = 0.43"""),
              {"c": cid})
    s.execute(text("""INSERT INTO sc_commodity_calibration (commodity_id, origin, hazard_driver) VALUES (:c, 'ES41', 'drought')
                      ON CONFLICT (commodity_id, origin) DO UPDATE SET hazard_driver = 'drought'"""), {"c": cid})
    tier = s.execute(text("SELECT calibration_tier FROM v_sc_commodity_calibration WHERE commodity_id = :c AND "
                          "origin = 'ES41'"), {"c": cid}).scalar()
    assert tier == "indicative"
