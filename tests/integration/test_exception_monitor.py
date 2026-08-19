"""Exception Monitor — sweeps live filings for failing checks and spins de-duped tasks."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.governance.exception_monitor import exceptions, spin_task

BANK_ORG = "11111111-1111-4111-8111-111111111111"


@pytest.mark.integration
def test_monitor_lists_only_failing_checks_over_live_filings():
    with get_session() as s:
        d = exceptions(s, BANK_ORG)
        assert set(d["summary"]) >= {"total", "blocking", "warnings", "tracked", "filings_scanned"}
        # every listed exception is a real failing check of a gating severity
        for e in d["exceptions"]:
            assert e["severity"] in ("blocking", "warning")
            assert e["criticality"] in ("critical", "high")
            assert e["source_ref"].startswith(e["filing_id"])
        s.rollback()


@pytest.mark.integration
def test_spin_task_is_idempotent_per_exception():
    with get_session() as s:
        u = str(s.execute(text("SELECT user_id FROM users WHERE email='admin@meridian.demo'")).scalar())
        d = exceptions(s, BANK_ORG)
        if not d["exceptions"]:
            pytest.skip("no open exceptions to spin")
        e = d["exceptions"][0]
        t1 = spin_task(s, BANK_ORG, u, filing_id=e["filing_id"], rule=e["rule"],
                       message=e["message"], severity=e["severity"])
        t2 = spin_task(s, BANK_ORG, u, filing_id=e["filing_id"], rule=e["rule"],
                       message=e["message"], severity=e["severity"])
        assert t1["task_id"] == t2["task_id"]                 # same exception → one task
        assert t1["source"] == "validation" and t1["filing_id"] == e["filing_id"]
        s.rollback()
