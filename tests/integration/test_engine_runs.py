"""Intake phase 4: every freeze records the engine run — what it read, and the checks its output passed.

  * a freeze writes a run and the snapshot names it; the input manifest counts the book, totals it, fingerprints it
  * the fingerprint is stable when nothing changed and moves when one fact changes
  * integrity failures refuse the freeze — a lost asset, a stranger, totals that do not add up, a NaN
  * an undecided difference between the client's values and ours is a warning kept on the run
Runs inside a rolled-back transaction."""
from __future__ import annotations

import copy

import pytest
from sqlalchemy import text

from services.governance import engine_runs as R
from services.governance.filings import reporting_period_end
from services.governance.report_snapshots import create_snapshot
from services.intake import observations as O
from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration


def _freeze(s):
    return create_snapshot(s, BANK_ORG, "bank_tcfd", None, period_end=reporting_period_end(s, BANK_ORG))


def test_a_freeze_records_its_run_and_the_snapshot_names_it(session_rolled_back):
    s = session_rolled_back
    snap = _freeze(s)
    assert snap["run_status"] in ("pass", "warn")
    rid = s.execute(text("SELECT run_id::text FROM report_snapshots WHERE snapshot_id = CAST(:s AS uuid)"),
                    {"s": snap["snapshot_id"]}).scalar()
    run = R.get_run(s, BANK_ORG, rid)
    book = run["inputs"]["books"][0]
    n, total = s.execute(text("""SELECT count(*), sum(primary_value_eur) FROM portfolio_entities
                                 WHERE org_id = CAST(:o AS uuid) AND vertical = 'banking' AND source = 'own'"""), {"o": BANK_ORG}).one()
    assert book["book"] == "bank_assets" and book["n_assets"] == n and book["total_value_eur"] == pytest.approx(float(total), abs=0.01)
    assert {c["key"] for c in run["checks"]} >= {"finite", "identity", "totals", "input_tie", "differences", "feeds"}
    assert "scored" not in {c["key"] for c in run["checks"]}      # the Taxonomy templates read no physical-risk score (E95)
    assert all(c["status"] != "fail" for c in run["checks"]) and run["view"] == "joint"


def test_the_fingerprint_moves_only_when_a_fact_changes(session_rolled_back):
    s = session_rolled_back
    a, _ = R.inputs(s, BANK_ORG, "bank_tcfd")
    b, _ = R.inputs(s, BANK_ORG, "bank_tcfd")
    assert R._sha(a) == R._sha(b)
    s.execute(text("""UPDATE portfolio_entities SET year_built = COALESCE(year_built, 1990) + 1 WHERE entity_id = (
                        SELECT entity_id FROM portfolio_entities WHERE org_id = CAST(:o AS uuid) AND vertical = 'banking'
                        AND source = 'own' LIMIT 1)"""), {"o": BANK_ORG})
    c, _ = R.inputs(s, BANK_ORG, "bank_tcfd")
    assert c["books"][0]["facts_sha256"] != a["books"][0]["facts_sha256"] and R._sha(c) != R._sha(a)


@pytest.mark.parametrize("tamper,key", [
    (lambda p: p["assets"].pop(), "identity"),                                       # an asset lost on the way
    (lambda p: p["assets"].append({**p["assets"][0], "asset_id": "00000000-0000-0000-0000-000000000000"}), "identity"),
    (lambda p: p["rollup"].__setitem__("total_value_eur", p["rollup"]["total_value_eur"] + 1e6), "totals"),
    (lambda p: p["rollup"].__setitem__("pct_value_at_risk", float("nan")), "finite"),
])
def test_an_output_that_does_not_hold_is_refused(session_rolled_back, tamper, key):
    s = session_rolled_back
    from api.routers.bank import build_disclosure_snapshot
    payload = copy.deepcopy(build_disclosure_snapshot(s, BANK_ORG, "baseline", "current"))
    payload["_fx"] = {"presentation_currency": "EUR"}
    tamper(payload)
    before = s.execute(text("SELECT count(*) FROM engine_runs")).scalar()
    with pytest.raises(R.RunCheckError) as e:
        R.record(s, BANK_ORG, "bank_tcfd", None, basis={}, payload=payload)
    assert any(c["key"] == key and c["status"] == "fail" for c in e.value.checks)
    assert s.execute(text("SELECT count(*) FROM engine_runs")).scalar() == before     # nothing recorded


def test_an_undecided_difference_is_a_warning_on_the_run(session_rolled_back):
    s = session_rolled_back
    from tests.integration.berlin_asset import berlin_asset
    aid = berlin_asset(s, "FR")                                   # a Berlin asset booked in France
    O.sync(s, BANK_ORG, asset_ids=[aid])
    snap = _freeze(s)
    diff = next(c for c in snap["run_checks"] if c["key"] == "differences")
    assert snap["run_status"] == "warn" and diff["status"] == "warn" and int(diff["detail"].split()[0]) >= 1
    assert s.execute(text("SELECT 1 FROM asset_conflicts WHERE asset_id = CAST(:a AS uuid) AND status = 'open'"), {"a": aid}).first()
