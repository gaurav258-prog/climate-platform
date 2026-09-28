"""Intake phase 6: a frozen filing is pinned to its engine run; new data never touches it — it is flagged.

  * nothing changed → the filing says so
  * a fact changes on an asset in scope → flagged: the book's fingerprint moved, which fact, from which path; the frozen
    snapshot is byte-for-byte what it was
  * the task-feed sweep finds the flagged filing without opening it
  * a filing frozen before runs were recorded has no pin and says so
Runs inside a rolled-back transaction (generate / refresh commit, so commits become flushes here)."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from services.governance import data_revisions as D
from services.governance import filings as F
from services.intake import observations as O
from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration


@pytest.fixture()
def s(session_rolled_back):
    session_rolled_back.commit = session_rolled_back.flush
    yield session_rolled_back
    del session_rolled_back.commit


def _filing(s) -> str:
    s.execute(text("UPDATE regulatory_filing SET status = 'superseded' WHERE org_id = CAST(:o AS uuid) AND framework = 'bank_tcfd'"),
              {"o": BANK_ORG})
    token = F.preflight(s, BANK_ORG, "bank", "bank_tcfd")["confirm_token"]
    user = s.execute(text("SELECT user_id::text FROM users WHERE email = 'admin@meridian.demo'")).scalar()
    return F.generate_filing(s, BANK_ORG, "bank", "bank_tcfd", user, confirm_token=token)["filing_id"]


def _sha(s, fid):
    return s.execute(text("""SELECT rs.payload_sha256 FROM regulatory_filing rf JOIN report_snapshots rs ON rs.snapshot_id = rf.snapshot_id
                             WHERE rf.filing_id = CAST(:f AS uuid)"""), {"f": fid}).scalar()


def test_nothing_changed_is_said_plainly(s):
    fid = _filing(s)
    r = D.revisions(s, BANK_ORG, fid)
    assert r["pinned"] and r["changed"] is False and r["facts"]["n"] == 0 and "Nothing" in r["message"]


def test_a_changed_fact_flags_the_filing_and_leaves_it_untouched(s):
    fid = _filing(s)
    before = _sha(s, fid)
    aid = s.execute(text("""SELECT entity_id::text FROM portfolio_entities WHERE org_id = CAST(:o AS uuid) AND vertical = 'banking'
                            AND source = 'own' LIMIT 1"""), {"o": BANK_ORG}).scalar()
    s.execute(text("UPDATE portfolio_entities SET primary_value_eur = primary_value_eur + 1000 WHERE entity_id = CAST(:i AS uuid)"), {"i": aid})
    O.sync(s, BANK_ORG, asset_ids=[aid], method="manual_edit", origin="user:test")
    r = D.revisions(s, BANK_ORG, fid)
    assert r["changed"] and any(b["changed"] for b in r["books"])
    assert r["facts"]["by_field"].get("primary_value_eur") == 1 and r["facts"]["by_path"].get("manual_edit") == 1
    assert "restate" in r["message"] and _sha(s, fid) == before            # flagged, never touched
    flagged = D.flagged_filings(s, BANK_ORG)
    assert any(f["filing_id"] == fid and f["new_facts"] >= 1 for f in flagged)


def test_a_filing_without_a_run_says_it_has_no_pin(s):
    fid = _filing(s)
    s.execute(text("ALTER TABLE report_snapshots DISABLE TRIGGER USER"))
    s.execute(text("""UPDATE report_snapshots SET run_id = NULL WHERE snapshot_id =
                      (SELECT snapshot_id FROM regulatory_filing WHERE filing_id = CAST(:f AS uuid))"""), {"f": fid})
    s.execute(text("ALTER TABLE report_snapshots ENABLE TRIGGER USER"))
    r = D.revisions(s, BANK_ORG, fid)
    assert r["pinned"] is False and r["changed"] is None
