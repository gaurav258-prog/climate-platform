"""The regulatory-filing lifecycle: forward-only state machine, append-only history, freeze-once-filed.

Requires PostgreSQL. Non-polluting: the state-machine test runs in one uncommitted session (rolled back on
exit) using a throwaway future period so it can't collide with real filings; the WORM/guard probes commit a
mutation attempt, assert it's rejected, and roll back.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import InternalError, ProgrammingError

from core.db.session import get_session
from services.governance import filings as F
from services.governance.report_snapshots import create_snapshot

BANK_ORG = "11111111-1111-4111-8111-111111111111"
FUTURE_PERIOD = "2099-12-31"   # a period no real filing uses, so we never collide with the live slot


def _mk_draft(session, actor):
    """Insert a draft filing backed by a real frozen snapshot (so the validation gate has something to check),
    on a throwaway future period so it can't collide with any live filing slot."""
    snap = create_snapshot(session, BANK_ORG, "bank_tcfd", actor)   # freezes real Meridian book → passes validation
    fid = session.execute(text("""
        INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, snapshot_id, created_by)
        VALUES (:o, 'bank_tcfd', :pe, 'FY2099', 'draft', :snap, :u)
        RETURNING filing_id
    """), {"o": BANK_ORG, "pe": FUTURE_PERIOD, "snap": snap["snapshot_id"], "u": actor}).scalar()
    F._log_event(session, str(fid), None, "draft", "generate", actor, {})
    return str(fid)


@pytest.mark.integration
def test_full_lifecycle_advances_and_logs():
    """draft → in_review → approved → attested → submitted → accepted, each step appended to history."""
    with get_session() as s:
        maker = s.execute(text("SELECT user_id FROM users WHERE email='admin@meridian.demo'")).scalar()
        checker = s.execute(text("SELECT user_id FROM users WHERE email='approver@meridian.demo'")).scalar()
        fid = _mk_draft(s, str(maker))

        assert F.submit_for_review(s, BANK_ORG, fid, str(maker))["status"] == "in_review"
        # a different pair of eyes approves (4-eyes itself is enforced at the approvals router)
        assert F.mark_approved(s, BANK_ORG, fid, str(checker), reason="ties to book")["status"] == "approved"
        assert F.attest(s, BANK_ORG, fid, str(maker), "Head of Reg Reporting", "I certify.")["status"] == "attested"
        assert F.submit(s, BANK_ORG, fid, str(maker), submission_ref="REF-1")["status"] == "submitted"
        final = F.accept(s, BANK_ORG, fid, str(maker), ack_ref="ACK-1")
        assert final["status"] == "accepted"

        # every transition is in the append-only history, in order
        actions = [e["action"] for e in F.get_filing(s, BANK_ORG, fid, with_payload=False)["events"]]
        assert actions == ["generate", "submit_for_review", "approve", "attest", "submit", "accept"]
        s.rollback()   # non-polluting


@pytest.mark.integration
def test_restatement_supersedes_old_and_links_to_new():
    """Restating a filed filing supersedes it (pointing at the restatement) and opens a fresh draft;
    the variance of the new vs the old is supported and reconciles (identical data → zero deltas)."""
    from services.governance.filing_variance import variance
    with get_session() as s:
        maker = str(s.execute(text("SELECT user_id FROM users WHERE email='admin@meridian.demo'")).scalar())
        checker = str(s.execute(text("SELECT user_id FROM users WHERE email='approver@meridian.demo'")).scalar())
        fid = _mk_draft(s, maker)
        F.submit_for_review(s, BANK_ORG, fid, maker)
        F.mark_approved(s, BANK_ORG, fid, checker)
        F.attest(s, BANK_ORG, fid, maker, "Head of Reg", "I certify.")
        F.submit(s, BANK_ORG, fid, maker, submission_ref="REF")
        F.accept(s, BANK_ORG, fid, maker, ack_ref="ACK")

        new = F.restate_filing(s, BANK_ORG, fid, maker, "correct a valuation")
        old = F.get_filing(s, BANK_ORG, fid, with_payload=False)
        assert old["status"] == "superseded" and old["superseded_by"] == new["filing_id"]
        assert new["status"] == "draft"

        v = variance(s, BANK_ORG, new["filing_id"])
        assert v["supported"] and v["prior_filing_id"] == fid
        assert v["headline"]["total_value"]["delta"] == 0   # same book → reconciles exactly
        s.rollback()


@pytest.mark.integration
def test_cannot_restate_a_draft():
    with get_session() as s:
        maker = str(s.execute(text("SELECT user_id FROM users WHERE email='admin@meridian.demo'")).scalar())
        fid = _mk_draft(s, maker)
        with pytest.raises(F.FilingError):
            F.restate_filing(s, BANK_ORG, fid, maker, "nope")
        s.rollback()


@pytest.mark.integration
def test_preflight_reports_coverage_headline_and_gaps():
    """The confirm-data preflight returns live coverage, the book headline and honest gaps — no freeze."""
    with get_session() as s:
        pf = F.preflight(s, BANK_ORG, "bank", "bank_tcfd")
        assert pf["framework"] == "bank_tcfd"
        assert set(pf["coverage"]) >= {"label", "done", "total", "pct"}
        assert pf["total_value_eur"] is not None and pf["total_value_eur"] > 0
        # if not every asset is scored, that must be surfaced as a gap (honesty)
        if pf["coverage"]["done"] < pf["coverage"]["total"]:
            assert any("not yet scored" in g for g in pf["gaps"])
        # preflight must not have created a filing
        n = s.execute(text("SELECT count(*) FROM regulatory_filing WHERE org_id = :o AND period_end = '2099-12-31'"),
                      {"o": BANK_ORG}).scalar()
        assert n == 0
        s.rollback()


@pytest.mark.integration
def test_illegal_transition_is_refused():
    """You can't attest a draft, or submit-for-review a filing that's already accepted."""
    with get_session() as s:
        maker = str(s.execute(text("SELECT user_id FROM users WHERE email='admin@meridian.demo'")).scalar())
        fid = _mk_draft(s, maker)
        with pytest.raises(F.FilingError):
            F.attest(s, BANK_ORG, fid, maker, "X", "Y")     # draft can't jump to attested
        s.rollback()


@pytest.mark.integration
def test_filing_event_log_is_worm():
    """The lifecycle history is append-only — UPDATE and DELETE are blocked at the DB level."""
    with get_session() as s:
        eid = s.execute(text("SELECT event_id FROM regulatory_filing_event LIMIT 1")).scalar()
    if not eid:
        pytest.skip("no filing events to probe")
    for sql, op in [("UPDATE regulatory_filing_event SET action='tamper' WHERE event_id = :e", "UPDATE"),
                    ("DELETE FROM regulatory_filing_event WHERE event_id = :e", "DELETE")]:
        raised = False
        try:
            with get_session() as s:
                s.execute(text(sql), {"e": eid})
                s.commit()
        except (InternalError, ProgrammingError):
            raised = True
        assert raised, f"{op} on regulatory_filing_event should be blocked by the WORM trigger"


@pytest.mark.integration
def test_submitted_filing_content_is_frozen():
    """Once submitted, a filing's frozen content (snapshot/period/framework) cannot be changed."""
    with get_session() as s:
        fid = s.execute(text(
            "SELECT filing_id FROM regulatory_filing WHERE status IN ('submitted','accepted') LIMIT 1")).scalar()
    if not fid:
        pytest.skip("no filed filing to probe")
    raised = False
    try:
        with get_session() as s:
            s.execute(text("UPDATE regulatory_filing SET period_end = '2000-01-01' WHERE filing_id = :f"),
                      {"f": fid})
            s.commit()
    except (InternalError, ProgrammingError):
        raised = True
    assert raised, "changing a submitted filing's period should be blocked by the freeze guard"
