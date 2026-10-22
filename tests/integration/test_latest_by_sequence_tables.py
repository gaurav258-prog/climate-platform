"""E315 — the ten tables E312 left on its worklist. Rolled back throughout; every pair below is written in one transaction,
so the two rows share now() and only the order they were written can say which is the latest.

  feed_refresh_log    a feed's latest refresh is the last one written
  gl_balance          the latest ledger batch is the last one uploaded
  ingest_batches      the last batch imported is the last import, whichever batch was received first
  reg_submission_case a filing's case is the one with the latest activity on its thread
  reg_alert           each detected change has its own alert, read by its key
  price index         the freshest month decides the series; two publishers at that month are named"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("first, second", [("failed", "refreshed"), ("refreshed", "failed")])
def test_a_feeds_latest_refresh_is_the_last_written(session_rolled_back, first, second):
    from services.data.feeds import feed_freshness
    s = session_rolled_back
    for status in (first, second):
        s.execute(text("INSERT INTO feed_refresh_log (feed_key, status) VALUES ('flood', :s)"), {"s": status})
    flood = next(f for f in feed_freshness(s) if f["key"] == "flood")
    assert (flood["status"] == "failed") is (second == "failed")


def test_the_latest_ledger_batch_is_the_last_uploaded(session_rolled_back):
    from services.governance.gl_recon import _latest_batch
    s = session_rolled_back
    batches = [str(uuid.uuid4()) for _ in range(2)]
    for b in batches:
        s.execute(text("""INSERT INTO gl_balance (gl_id, org_id, batch_id, account_code, balance_eur)
                          VALUES (gen_random_uuid(), CAST(:o AS uuid), CAST(:b AS uuid), '1000', 1)"""), {"o": BANK_ORG, "b": b})
    assert _latest_batch(s, BANK_ORG)["b"] == batches[1]


def _batch(s, state: str = "received") -> str:
    return s.execute(text("""INSERT INTO ingest_batches (org_id, template, sha256, state, gate_status)
                             VALUES (CAST(:o AS uuid), 'banking_loans', :h, :st, 'pass') RETURNING batch_id::text"""),
                     {"o": BANK_ORG, "h": uuid.uuid4().hex, "st": state}).scalar()


def test_the_last_batch_imported_is_the_last_import(session_rolled_back):
    s = session_rolled_back
    early, late = _batch(s), _batch(s)                         # received in this order …
    for b in (late, early):                                     # … imported the other way round
        s.execute(text("UPDATE ingest_batches SET state = 'imported', imported_at = now() WHERE batch_id = CAST(:b AS uuid)"),
                  {"b": b})
    last = s.execute(text("""SELECT batch_id::text FROM ingest_batches WHERE org_id = CAST(:o AS uuid) AND state = 'imported'
                             ORDER BY imported_seq DESC LIMIT 1"""), {"o": BANK_ORG}).scalar()
    assert last == early
    seq = s.execute(text("SELECT imported_seq FROM ingest_batches WHERE batch_id = CAST(:b AS uuid)"), {"b": early}).scalar()
    s.execute(text("UPDATE ingest_batches SET imported_seq = imported_seq + 1000, ingest_notes = '{}' WHERE batch_id = CAST(:b AS uuid)"),
              {"b": early})
    assert s.execute(text("SELECT imported_seq FROM ingest_batches WHERE batch_id = CAST(:b AS uuid)"), {"b": early}).scalar() == seq
    assert s.execute(text("SELECT imported_seq FROM ingest_batches WHERE batch_id = CAST(:b AS uuid)"),
                     {"b": _batch(s)}).scalar() is None      # not imported: no place in the import order


def test_a_filings_case_is_the_one_with_the_latest_activity(session_rolled_back):
    from services.governance import transmission as T
    s = session_rolled_back
    fid = s.execute(text("SELECT filing_id::text FROM regulatory_filing WHERE org_id = CAST(:o AS uuid) LIMIT 1"),
                    {"o": BANK_ORG}).scalar()
    if fid is None:
        pytest.skip("no bank filing on this machine")
    actor = s.execute(text("SELECT user_id::text FROM users WHERE org_id = CAST(:o AS uuid) LIMIT 1"), {"o": BANK_ORG}).scalar()
    older = T.open_case(s, BANK_ORG, actor, regulator="Probe authority A", filing_id=fid)["case_id"]
    newer = T.open_case(s, BANK_ORG, actor, regulator="Probe authority B", filing_id=fid)["case_id"]
    assert T.case_for_filing(s, BANK_ORG, fid)["case_id"] == newer
    T.post_message(s, BANK_ORG, older, actor, direction="inbound", author="Probe authority A", body="A question.")
    assert T.case_for_filing(s, BANK_ORG, fid)["case_id"] == older


def test_each_detected_change_has_its_own_alert(session_rolled_back):
    from services.governance.reg_alerts import alert_key
    from services.governance.reg_impact_links import change_impacts
    s = session_rolled_back
    changes = [{"framework": "bank_tcfd", "celex": f"3{n}PROBE", "date": "2027-01-01", "source": "detected"} for n in (1, 2)]
    assert alert_key(changes[0]) != alert_key(changes[1])     # same framework, same date: two changes, two alerts
    tasks = {}
    for c in changes:
        s.execute(text("""INSERT INTO reg_detected_change (framework, celex, title, effective_date)
                          VALUES (:f, :c, 'probe', '2027-01-01')"""), {"f": c["framework"], "c": c["celex"]})
        tasks[c["celex"]] = str(uuid.uuid4())
        s.execute(text("""INSERT INTO reg_alert (org_id, alert_key, framework, kind, title, task_id)
                          VALUES (CAST(:o AS uuid), :k, :f, 'detected', 'probe', CAST(:t AS uuid))"""),
                  {"o": BANK_ORG, "k": alert_key(c), "f": c["framework"], "t": tasks[c["celex"]]})
    got = {ch["celex"]: ch["task_id"] for ch in change_impacts(s, BANK_ORG, "bank")["changes"] if ch["celex"] in tasks}
    assert got == tasks


def test_two_publishers_at_the_latest_month_are_named_not_chosen(session_rolled_back):
    from services.intelligence.price_index import _shock
    s = session_rolled_back
    rows = [("Publisher A", "2026-08", 100), ("Publisher A", "2026-09", 110), ("Publisher B", "2026-07", 90)]
    for src, ym, v in rows:
        s.execute(text("""INSERT INTO commodity_price_index (price_id, source, commodity, period_ym, index_value, unit, currency)
                          VALUES (gen_random_uuid(), :s, 'probe grain', :p, :v, 'EUR/t', 'EUR')"""), {"s": src, "p": ym, "v": v})
    assert _shock(s, "probe grain")["source"] == "Publisher A"      # the freshest month decides, not the last loaded
    s.execute(text("""INSERT INTO commodity_price_index (price_id, source, commodity, period_ym, index_value, unit, currency)
                      VALUES (gen_random_uuid(), 'Publisher B', 'probe grain', '2026-09', 95, 'EUR/t', 'EUR')"""))
    out = _shock(s, "probe grain")
    assert out["usable"] is False and out["reason_code"] == "agri.data.price.two_publishers"
    assert out["reason_params"]["publishers"] == "Publisher A and Publisher B"
