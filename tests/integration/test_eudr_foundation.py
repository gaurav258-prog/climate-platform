"""EUDR layer 1 (E90): the records Regulation (EU) 2023/1115 asks for hold their rules in the database, whatever writes
them. One rolled-back transaction per test (Terra Foods: a cocoa plot and a supplier).

  undertaking statement  four eyes; append-only
  movement               customs goods need kilograms of net mass (Annex II point 2); some quantity always; an HS code
                         is 4, 6, 8 or 10 digits; a supplementary unit comes with its quantity
  production             a date range runs forward (Art. 9(1)(d))
  assessment             append-only; 'not assessable' says why — and it is a reading, never a verdict
  reference              one reference number once; append-only
  filing                 the movement is the statement's subject; a movement in a statement under review is frozen;
                         two funds' documents for one period are two live filings (the old one-filing rule refused it)
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.integration
TERRA = "55555555-5555-4555-8555-555555555555"
NORDKAP = "44444444-4444-4444-8444-444444444444"


def _raises(s, sql, params=None, match=""):
    with pytest.raises(DBAPIError, match=match):
        with s.begin_nested():
            s.execute(text(sql), params or {})


def _movement(s, **over) -> str:
    row = {"o": TERRA, "kind": "placing", "role": "operator", "d": "2027-01-15", "hs": "180100", "desc": "Cocoa beans, whole",
           "cf": True, "kg": 25000, **over}
    return str(s.execute(text("""
        INSERT INTO eudr_movement (org_id, kind, actor_role, planned_on, hs_code, description, customs_flow, net_mass_kg)
        VALUES (CAST(:o AS uuid), :kind, :role, :d, :hs, :desc, :cf, :kg) RETURNING movement_id"""), row).scalar())


def _plot(s) -> str:
    return str(s.execute(text("""SELECT p.plot_id FROM sc_sourcing_plots p JOIN sc_commodities c USING (commodity_id)
                                 WHERE p.org_id = CAST(:o AS uuid) AND c.eudr_covered LIMIT 1"""), {"o": TERRA}).scalar())


def test_the_undertaking_statement_needs_two_people_and_is_kept(session_rolled_back):
    s = session_rolled_back
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    sql = """INSERT INTO eudr_undertaking_statement (org_id, effective_from, size_class, country, eori, requested_by, approved_by)
             VALUES (CAST(:o AS uuid), '2026-12-30', 'large', 'ES', 'ESB12345678', CAST(:a AS uuid), CAST(:b AS uuid))"""
    _raises(s, sql, {"o": TERRA, "a": a, "b": a}, "four_eyes")
    _raises(s, sql.replace("'ESB12345678'", "'not an eori'"), {"o": TERRA, "a": a, "b": b}, "ck_eudr_eori")
    s.execute(text(sql), {"o": TERRA, "a": a, "b": b})
    _raises(s, "UPDATE eudr_undertaking_statement SET size_class = 'small' WHERE org_id = CAST(:o AS uuid)", {"o": TERRA},
            "append-only")


def test_a_movement_states_what_the_annexes_ask(session_rolled_back):
    s = session_rolled_back
    _raises(s, "INSERT INTO eudr_movement (org_id, kind, actor_role, planned_on, hs_code, description, customs_flow, volume_m3) "
               "VALUES (CAST(:o AS uuid), 'placing', 'operator', '2027-01-15', '180100', 'x', true, 10)", {"o": TERRA},
            "ck_eudr_customs_mass")
    _raises(s, "INSERT INTO eudr_movement (org_id, kind, actor_role, planned_on, hs_code, description, customs_flow) "
               "VALUES (CAST(:o AS uuid), 'placing', 'operator', '2027-01-15', '180100', 'x', false)", {"o": TERRA},
            "ck_eudr_quantity")
    with pytest.raises(DBAPIError, match="ck_eudr_hs"):
        with s.begin_nested():
            _movement(s, hs="1801 00")
    with pytest.raises(DBAPIError, match="ck_eudr_role"):
        with s.begin_nested():
            _movement(s, role="broker")
    m = _movement(s)
    _raises(s, "UPDATE eudr_movement SET supplementary_unit = 'p/st' WHERE movement_id = CAST(:m AS uuid)", {"m": m},
            "ck_eudr_supp_pair")
    _raises(s, "INSERT INTO eudr_movement_plot VALUES (CAST(:m AS uuid), CAST(:p AS uuid), '2025-06-30', '2025-01-01')",
            {"m": m, "p": _plot(s)}, "ck_eudr_production")


def test_a_plot_reading_is_kept_and_is_never_a_verdict(session_rolled_back):
    s = session_rolled_back
    p = _plot(s)
    sql = """INSERT INTO eudr_plot_assessment (plot_id, dataset, dataset_version, geometry_sha256, cutoff, outcome, reason)
             VALUES (CAST(:p AS uuid), 'hansen_gfc', 'v1.12', 'abc', '2020-12-31', :o, :r)"""
    _raises(s, sql, {"p": p, "o": "non_compliant", "r": None}, "ck_eudr_outcome")
    _raises(s, sql, {"p": p, "o": "not_assessable", "r": None}, "ck_eudr_unassessable")
    s.execute(text(sql), {"p": p, "o": "loss_after_cutoff", "r": None})
    _raises(s, "DELETE FROM eudr_plot_assessment WHERE plot_id = CAST(:p AS uuid)", {"p": p}, "append-only")


def _filing(s, org, status, **subject) -> str:
    return str(s.execute(text("""
        INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, entity_id, fund_id, eudr_movement_id,
                                       filing_role)
        VALUES (CAST(:o AS uuid), :fw, '2027-12-31', CASE WHEN :fw = 'eudr_dds' THEN 'T · 2027-12-31' ELSE 'FY2027' END, :st, NULL, CAST(:f AS uuid), CAST(:m AS uuid), :role)
        RETURNING filing_id"""), {"o": org, "st": status, "fw": subject.get("fw", "eudr_dds"), "f": subject.get("fund"),
                                  "m": subject.get("movement"), "role": subject.get("role")}).scalar())


def test_a_movement_under_review_is_frozen_and_each_movement_has_its_own_filing(session_rolled_back):
    s = session_rolled_back
    m1, m2 = _movement(s), _movement(s, kg=4000)
    f1 = _filing(s, TERRA, "draft", movement=m1)
    s.execute(text("UPDATE eudr_movement SET net_mass_kg = 26000 WHERE movement_id = CAST(:m AS uuid)"), {"m": m1})  # a draft: editable
    _filing(s, TERRA, "draft", movement=m2)                      # a second movement in the same period: its own live filing
    s.execute(text("UPDATE regulatory_filing SET status = 'in_review' WHERE filing_id = CAST(:f AS uuid)"), {"f": f1})
    _raises(s, "UPDATE eudr_movement SET net_mass_kg = 1 WHERE movement_id = CAST(:m AS uuid)", {"m": m1}, "cannot change")
    _raises(s, "INSERT INTO eudr_movement_plot VALUES (CAST(:m AS uuid), CAST(:p AS uuid), '2025-01-01', '2025-06-30')",
            {"m": m1, "p": _plot(s)}, "cannot change")
    s.execute(text("INSERT INTO eudr_dds_reference (filing_id, reference_number, verification_number, source) "
                   "VALUES (CAST(:f AS uuid), '27ESZZZ0000001', 'VZ9', 'manual_entry')"), {"f": f1})
    _raises(s, "INSERT INTO eudr_dds_reference (filing_id, reference_number, source) "
               "VALUES (CAST(:f AS uuid), '27ESZZZ0000001', 'manual_entry')", {"f": f1}, "ux_eudr_reference")
    _raises(s, "UPDATE eudr_dds_reference SET verification_number = 'X' WHERE filing_id = CAST(:f AS uuid)", {"f": f1},
            "append-only")


def test_two_funds_documents_for_one_period_are_two_live_filings(session_rolled_back):
    s = session_rolled_back
    funds = [str(s.execute(text("""INSERT INTO funds (org_id, name, fund_type, sfdr_classification)
                                   VALUES (CAST(:o AS uuid), :n, 'fund', 'article_8') RETURNING fund_id"""),
                           {"o": NORDKAP, "n": f"E90 fund {i}"}).scalar()) for i in (1, 2)]
    for f in funds:
        _filing(s, NORDKAP, "draft", fw="sfdr_periodic", fund=f, role="product")
    with pytest.raises(DBAPIError, match="ux_reg_filing_live"):
        with s.begin_nested():
            _filing(s, NORDKAP, "draft", fw="sfdr_periodic", fund=funds[0], role="product")
