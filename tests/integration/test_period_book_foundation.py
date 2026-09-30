"""The reporting year in the database (period_book_foundation_20260930), proved on the real schema in one rolled-back
transaction: dated assets and site area, enforced entity links, year-end values append-only with the latest live,
the year-end close (four eyes, append-only) refusing period values without a restatement reason, sites and
undertakings with reporting history not deleted, snapshot versions counted per period and undertaking, and
protected-area loads kept with only the current one read.
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.integration
ORG = "0bbe0bbe-0000-4000-8000-0000000fa110"


def _refused(s, sql: str, params: dict | None = None, match: str = "") -> str:
    with pytest.raises(DBAPIError) as e:
        with s.begin_nested():
            s.execute(text(sql), params or {})
    assert match in str(e.value), str(e.value)
    return str(e.value)


def _user(s, tag: str) -> str:
    uid = str(uuid.uuid4())
    s.execute(text("""INSERT INTO users (user_id, org_id, email, full_name, role)
                      VALUES (CAST(:u AS uuid), CAST(:o AS uuid), :e, :n, 'analyst')"""),
              {"u": uid, "o": ORG, "e": f"{tag}-{uid[:8]}@probe.test", "n": tag})
    return uid


@pytest.fixture()
def book(session_rolled_back):
    s = session_rolled_back
    s.execute(text("INSERT INTO organizations (org_id, name, type, country) VALUES (CAST(:o AS uuid), 'period probe', 'agriculture', 'ES')"),
              {"o": ORG})
    ent = s.execute(text("""INSERT INTO reporting_entities (entity_id, org_id, name) VALUES (gen_random_uuid(), CAST(:o AS uuid), 'Probe SA')
                            RETURNING entity_id::text"""), {"o": ORG}).scalar()
    site = s.execute(text("""INSERT INTO sc_company_sites (org_id, name, entity_id, held_from, area_ha)
                             VALUES (CAST(:o AS uuid), 'Mill', CAST(:e AS uuid), '2019-03-01', 12.5) RETURNING site_id::text"""),
                     {"o": ORG, "e": ent}).scalar()
    return s, ent, site


def test_assets_carry_their_dates_and_area_and_real_links(book):
    s, ent, site = book
    _refused(s, "UPDATE sc_company_sites SET held_until = '2018-01-01' WHERE site_id = CAST(:i AS uuid)", {"i": site}, "ck_site_held")
    _refused(s, "UPDATE sc_company_sites SET area_ha = -1 WHERE site_id = CAST(:i AS uuid)", {"i": site}, "ck_site_area_ha")
    _refused(s, "UPDATE sc_company_sites SET entity_id = gen_random_uuid() WHERE site_id = CAST(:i AS uuid)", {"i": site}, "fk_site_entity")
    _refused(s, "INSERT INTO sc_company_sites (org_id, name) VALUES (gen_random_uuid(), 'orphan')", match="fk_site_org")


def test_year_end_values_are_append_only_and_the_latest_is_live(book):
    s, ent, site = book
    ins = """INSERT INTO site_period_values (org_id, site_id, reporting_entity_id, period_end, measure, amount, currency,
                                             amount_eur, source, restatement_reason)
             VALUES (CAST(:o AS uuid), CAST(:s AS uuid), CAST(:e AS uuid), '2025-12-31', 'carrying_amount', :a, 'EUR', :a, 'client', :r)"""
    s.execute(text(ins), {"o": ORG, "s": site, "e": ent, "a": 1_000_000, "r": None})
    s.execute(text(ins), {"o": ORG, "s": site, "e": ent, "a": 1_200_000, "r": None})
    live = s.execute(text("SELECT amount FROM v_site_period_values_live WHERE site_id = CAST(:s AS uuid)"), {"s": site}).scalars().all()
    assert [float(x) for x in live] == [1_200_000]
    _refused(s, "UPDATE site_period_values SET amount = 1 WHERE site_id = CAST(:s AS uuid)", {"s": site}, "append-only")
    _refused(s, "DELETE FROM site_period_values WHERE site_id = CAST(:s AS uuid)", {"s": site}, "append-only")
    _refused(s, ins.replace("'carrying_amount'", "'market_value'"), {"o": ORG, "s": site, "e": ent, "a": 1, "r": None}, "ck_site_period_measure")

    # a site with year-end values is part of the reporting history: it stops being held, it is not deleted
    from services.governance.entities import EntityError, delete_entity
    from services.governance.location_governance import (
        LocationChangeError,
        deletion_block,
        submit_or_apply,
    )
    assert "held until" in deletion_block(s, "site", site)
    with pytest.raises(LocationChangeError):
        submit_or_apply(s, org_id=ORG, actor_user_id=_user(s, "maker"), request_type="supply.site.delete",
                        target_id=site, title="delete")
    with pytest.raises(EntityError, match="reporting history"):
        delete_entity(s, ORG, ent)


def test_the_year_end_close_is_four_eyes_and_append_only_and_turns_new_values_into_restatements(book):
    s, ent, site = book
    maker, checker = _user(s, "maker"), _user(s, "checker")
    close = """INSERT INTO reporting_period_close (org_id, reporting_entity_id, period_end, requested_by, approved_by)
               VALUES (CAST(:o AS uuid), CAST(:e AS uuid), '2025-12-31', CAST(:m AS uuid), CAST(:c AS uuid))"""
    _refused(s, close, {"o": ORG, "e": ent, "m": maker, "c": maker}, "ck_period_close_four_eyes")
    s.execute(text(close), {"o": ORG, "e": ent, "m": maker, "c": checker})
    _refused(s, close, {"o": ORG, "e": ent, "m": maker, "c": checker}, "ux_period_close")
    _refused(s, "UPDATE reporting_period_close SET note = 'x' WHERE org_id = CAST(:o AS uuid)", {"o": ORG}, "append-only")
    _refused(s, "DELETE FROM reporting_period_close WHERE org_id = CAST(:o AS uuid)", {"o": ORG}, "append-only")

    val = """INSERT INTO site_period_values (org_id, site_id, reporting_entity_id, period_end, measure, amount, currency,
                                             amount_eur, source, restatement_reason)
             VALUES (CAST(:o AS uuid), CAST(:s AS uuid), CAST(:e AS uuid), :pe, 'carrying_amount', 5, 'EUR', 5, 'client', :r)"""
    _refused(s, val, {"o": ORG, "s": site, "e": ent, "pe": "2025-12-31", "r": None}, "is closed")
    s.execute(text(val), {"o": ORG, "s": site, "e": ent, "pe": "2025-12-31", "r": "impairment found after the close"})
    s.execute(text(val), {"o": ORG, "s": site, "e": ent, "pe": "2026-12-31", "r": None})      # the next year is open

    prov = """INSERT INTO provided_datapoint (org_id, framework, datapoint_key, value_num, source, reporting_period_end,
                                              reporting_entity_id, restatement_reason)
              VALUES (CAST(:o AS uuid), 'esrs_pack', 'probe_key', 1, 'client', '2025-12-31', CAST(:e AS uuid), :r)"""
    _refused(s, prov, {"o": ORG, "e": ent, "r": None}, "is closed")
    s.execute(text(prov), {"o": ORG, "e": ent, "r": "metered figure corrected"})
    # the organisation itself (no entity) is a different undertaking: its period is not closed by the entity's close
    s.execute(text(prov.replace("CAST(:e AS uuid)", "NULL")), {"o": ORG, "r": None})


def test_snapshot_versions_are_counted_per_period_and_undertaking(book):
    s, ent, _ = book

    def snap(pe, e, v):
        s.execute(text("""INSERT INTO report_snapshots (org_id, report_type, version, reporting_basis, payload)
                          VALUES (CAST(:o AS uuid), 'esrs_pack', :v, CAST(:b AS jsonb), CAST(:p AS jsonb))"""),
                  {"o": ORG, "v": v, "b": json.dumps({"reporting_period_end": pe}),
                   "p": json.dumps({"_scope": {"reporting_entity_id": e}})})
    snap("2025-12-31", ent, 1)
    snap("2026-12-31", ent, 1)          # another year: its own v1
    snap("2025-12-31", None, 1)         # the organisation itself: its own v1
    _refused(s, """INSERT INTO report_snapshots (org_id, report_type, version, reporting_basis, payload)
                   VALUES (CAST(:o AS uuid), 'esrs_pack', 1, '{"reporting_period_end": "2025-12-31"}',
                           CAST(:p AS jsonb))""", {"o": ORG, "p": json.dumps({"_scope": {"reporting_entity_id": ent}})},
             "ux_report_snapshots_scope_version")
    got = s.execute(text("""SELECT period_end::text, reporting_entity_id::text FROM report_snapshots
                            WHERE org_id = CAST(:o AS uuid) ORDER BY 1, 2"""), {"o": ORG}).all()
    assert [tuple(r) for r in got] == [("2025-12-31", ent), ("2025-12-31", None), ("2026-12-31", ent)]


def test_a_protected_layer_keeps_every_load_and_reads_the_current_one(session_rolled_back):
    s = session_rolled_back
    from services.reference.protected_layers import current_loads, load_layer
    first = load_layer(s, "probe_layer", "2024-12-31", "probe", [{"h3_cell": "881f1d4897fffff", "within_km": 1.0},
                                                                 {"h3_cell": "881f1d4897fffff", "within_km": 0.0}], 8)
    assert first["n_cells"] == 1                                    # one cell, the closest reading kept
    second = load_layer(s, "probe_layer", "2025-12-31", "probe", [{"h3_cell": "881f1d4893fffff", "within_km": 0.0}], 8)
    assert second["retired"] == first["load_id"]
    kept = s.execute(text("SELECT count(*) FROM protected_h3_cell WHERE dataset = 'probe_layer'")).scalar()
    now = s.execute(text("SELECT h3_cell FROM v_protected_h3_current WHERE dataset = 'probe_layer'")).scalars().all()
    assert kept == 2 and now == ["881f1d4893fffff"]
    assert [x["load_id"] for x in current_loads(s) if x["dataset"] == "probe_layer"] == [second["load_id"]]
