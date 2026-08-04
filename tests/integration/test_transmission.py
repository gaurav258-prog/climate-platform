"""Transmission ↔ filing wiring: a submission case opened for a filing is found by `case_for_filing`,
which is what lets the filing drawer link straight to its regulator case (and vice-versa).

Requires PostgreSQL. Non-polluting: everything runs in one uncommitted session on a throwaway future
period and is rolled back on exit.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.governance import transmission as T
from services.governance.report_snapshots import create_snapshot

BANK_ORG = "11111111-1111-4111-8111-111111111111"
OTHER_ORG = "22222222-2222-4222-8222-222222222222"   # any non-owning org id — must not see the case
FUTURE_PERIOD = "2099-12-31"


def _mk_filing(session, actor):
    snap = create_snapshot(session, BANK_ORG, "bank_tcfd", actor)
    return str(session.execute(text("""
        INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, snapshot_id, created_by)
        VALUES (:o, 'bank_tcfd', :pe, 'FY2099', 'draft', :snap, :u)
        RETURNING filing_id
    """), {"o": BANK_ORG, "pe": FUTURE_PERIOD, "snap": snap["snapshot_id"], "u": actor}).scalar())


@pytest.mark.integration
def test_case_for_filing_links_the_two_modules():
    """A filing with no case resolves to None; once a case is opened for it, the drawer can find it —
    tenant-scoped, so another org never sees it."""
    with get_session() as s:
        actor = str(s.execute(text("SELECT user_id FROM users WHERE email='admin@meridian.demo'")).scalar())
        fid = _mk_filing(s, actor)

        assert T.case_for_filing(s, BANK_ORG, fid) is None            # nothing opened yet

        c = T.open_case(s, BANK_ORG, actor, regulator="EBA", filing_id=fid)
        found = T.case_for_filing(s, BANK_ORG, fid)
        assert found is not None
        assert found["case_id"] == c["case_id"]
        assert found["regulator"] == "EBA"
        assert found["stage"] == "ready"

        assert T.case_for_filing(s, OTHER_ORG, fid) is None           # tenant isolation

        s.rollback()   # non-polluting
