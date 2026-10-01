"""Intake phase 5: the three views of the book, and per reported figure the client's number or ours.

  * tellumen view: our value wherever we derive one; client view: the client's own value, even where ours was adopted
  * a view is computed, never stored — the book is unchanged afterwards, and a commit inside a view is refused
  * a filing frozen in a view says so (basis, payload, run) and its output reflects it
  * where the client's attested figure and ours both exist, the filing reports the chosen one (the client's by default),
    both frozen side by side; the official form carries the chosen value
Runs inside a rolled-back transaction."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from services.governance import figure_views as FV
from services.governance.filings import reporting_period_end
from services.governance.report_snapshots import create_snapshot
from services.intake import conflicts as C
from services.intake import observations as O
from services.intake import views as V
from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration


def _berlin_asset_booked_in(s, country: str) -> str:
    aid = s.execute(text("""SELECT entity_id::text FROM portfolio_entities WHERE org_id = CAST(:o AS uuid) AND vertical = 'banking'
                            AND source = 'own' AND latitude BETWEEN 52.3 AND 52.7 AND longitude BETWEEN 13.2 AND 13.6 LIMIT 1"""),
                    {"o": BANK_ORG}).scalar()
    if not aid:
        pytest.skip("no seeded Berlin asset")
    s.execute(text("UPDATE portfolio_entities SET country = :c WHERE entity_id = CAST(:i AS uuid)"), {"c": country, "i": aid})
    return aid


def _country(s, aid):
    return s.execute(text("SELECT country FROM portfolio_entities WHERE entity_id = CAST(:i AS uuid)"), {"i": aid}).scalar()


def test_the_tellumen_view_reads_our_value_and_leaves_the_book_as_it_was(session_rolled_back):
    s = session_rolled_back
    aid = _berlin_asset_booked_in(s, "FR")
    O.sync(s, BANK_ORG)
    subs = V.substitutions(s, BANK_ORG, "tellumen")
    assert any(x["asset_id"] == aid and x["field"] == "country" and x["value"] == "DE" for x in subs)
    assert V.substitutions(s, BANK_ORG, "joint") == []
    seen, rec = V.in_view(s, BANK_ORG, "tellumen", lambda: _country(s, aid))
    assert seen == "DE" and rec["facts_changed"] >= 1 and rec["by_field"].get("country", 0) >= 1
    assert _country(s, aid) == "FR"                                   # the book is untouched


def test_the_client_view_puts_the_clients_value_back_where_ours_was_adopted(session_rolled_back):
    s = session_rolled_back
    aid = _berlin_asset_booked_in(s, "FR")
    O.sync(s, BANK_ORG, asset_ids=[aid])
    cid = s.execute(text("SELECT conflict_id::text FROM asset_conflicts WHERE asset_id = CAST(:a AS uuid) AND status = 'open'"),
                    {"a": aid}).scalar()
    maker = s.execute(text("SELECT user_id::text FROM users WHERE email = 'admin@meridian.demo'")).scalar()
    checker = s.execute(text("SELECT user_id::text FROM users WHERE email = 'approver@meridian.demo'")).scalar()
    out = C.resolve(s, BANK_ORG, cid, "tellumen", maker, None)
    payload = s.execute(text("SELECT payload FROM approval_requests WHERE request_id = CAST(:r AS uuid)"), {"r": out["approval_request_id"]}).scalar()
    C.apply_decision(s, BANK_ORG, payload, "approved", checker)
    assert _country(s, aid) == "DE"                                    # the book now holds ours
    seen, _ = V.in_view(s, BANK_ORG, "client", lambda: _country(s, aid))
    assert seen == "FR" and _country(s, aid) == "DE"


def test_a_commit_inside_a_view_is_refused(session_rolled_back):
    s = session_rolled_back
    aid = _berlin_asset_booked_in(s, "FR")
    with pytest.raises(V.ViewError):
        V.in_view(s, BANK_ORG, "tellumen", lambda: s.commit())
    assert _country(s, aid) == "FR"
    with pytest.raises(V.ViewError):
        V.in_view(s, BANK_ORG, "nonsense", lambda: None)


def test_a_filing_frozen_in_a_view_says_so_and_reflects_it(session_rolled_back):
    s = session_rolled_back
    aid = _berlin_asset_booked_in(s, "FR")
    snap = create_snapshot(s, BANK_ORG, "bank_tcfd", None, view="tellumen", period_end=reporting_period_end(s, BANK_ORG))
    row = s.execute(text("SELECT payload, reporting_basis, run_id::text FROM report_snapshots WHERE snapshot_id = CAST(:s AS uuid)"),
                    {"s": snap["snapshot_id"]}).mappings().first()
    asset = next(a for a in row["payload"]["assets"] if a["asset_id"] == aid)
    assert asset["country"] == "DE" and row["reporting_basis"]["view"] == "tellumen"
    assert row["payload"]["_view"]["view"] == "tellumen" and row["payload"]["_view"]["facts_changed"] >= 1
    assert s.execute(text("SELECT view FROM engine_runs WHERE run_id = CAST(:r AS uuid)"), {"r": row["run_id"]}).scalar() == "tellumen"
    assert all(c["status"] != "fail" for c in snap["run_checks"])     # inputs were read in the same view
    assert _country(s, aid) == "FR"


def _attest_financed_emissions(s, value: float):
    s.execute(text("""UPDATE provided_datapoint SET status = 'superseded' WHERE org_id = CAST(:o AS uuid)
                      AND framework = 'bank_p3esg' AND datapoint_key = 'p3_scope3' AND status <> 'superseded'"""),
              {"o": BANK_ORG})
    from services.governance.filings import reporting_period_end
    s.execute(text("""INSERT INTO provided_datapoint (org_id, framework, datapoint_key, value_num, unit, source, provider_name,
                                                      status, decided_at, reporting_period_end)
                      VALUES (CAST(:o AS uuid), 'bank_p3esg', 'p3_scope3', :v, 'tCO2e', 'client', 'Audited PCAF',
                              'attested', now(), :pe)"""), {"o": BANK_ORG, "v": value, "pe": reporting_period_end(s, BANK_ORG)})


def test_the_clients_attested_figure_is_reported_by_default_and_ours_on_request(session_rolled_back):
    # financed emissions are a figure of Pillar 3 (Template 1); the EU Taxonomy Art. 8 report prints none (E95)
    s = session_rolled_back
    _attest_financed_emissions(s, 123456.0)
    snap = create_snapshot(s, BANK_ORG, "bank_p3esg", None, period_end=reporting_period_end(s, BANK_ORG))
    figs = s.execute(text("SELECT payload->'_figures' FROM report_snapshots WHERE snapshot_id = CAST(:s AS uuid)"),
                     {"s": snap["snapshot_id"]}).scalar()
    f = next(x for x in figs if x["datapoint"] == "p3_scope3")
    assert f["reported"] == "client" and f["client_value"] == 123456.0 and f["form_key"] == "emissions.scope3"
    groups = [{"group": "g", "datapoints": [{"key": "emissions.scope3", "value": f["tellumen_value"], "source": "calculated"}]}]
    FV.apply_to_form(groups, figs)
    d = groups[0]["datapoints"][0]
    assert d["value"] == 123456.0 and d["source"] == "provided" and d["figure"]["tellumen_value"] == f["tellumen_value"]
    if f["tellumen_value"] is not None:                                # ours exists: it can be the reported figure
        snap2 = create_snapshot(s, BANK_ORG, "bank_p3esg", None, figure_sources={"p3_scope3": "tellumen"}, period_end=reporting_period_end(s, BANK_ORG))
        figs2 = s.execute(text("SELECT payload->'_figures' FROM report_snapshots WHERE snapshot_id = CAST(:s AS uuid)"),
                          {"s": snap2["snapshot_id"]}).scalar()
        assert next(x for x in figs2 if x["datapoint"] == "p3_scope3")["reported"] == "tellumen"
