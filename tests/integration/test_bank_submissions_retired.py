"""The separate bank disclosure submission mechanism is retired (E99): it froze the bank's whole disclosure snapshot under
its own framework field, outside the filing lifecycle. Its routes are gone, no new release request is accepted, and a
legacy draft still pending can only be rejected — which closes it. Released records stay as they are in the database
(append-only by trigger). Inside one rolled-back transaction; the legacy draft is stated here.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.integration.conftest import login as _login
from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


def test_the_routes_are_gone_and_no_code_freezes_outside_the_lifecycle(api):
    maker = _login(api, "admin@meridian.demo", "Demo!admin1")
    for path in ("/v1/bank/submissions", "/v1/bank/submissions/trend"):
        assert api.get(path, headers=maker).status_code == 404
    assert api.post("/v1/bank/submissions", headers=maker, json={}).status_code in (404, 405)
    assert not (ROOT / "api/routers/bank_submissions.py").exists()
    writers = [str(f.relative_to(ROOT)) for d in ("api", "services", "scripts", "ml") for f in (ROOT / d).rglob("*.py")
               if "INSERT INTO bank_disclosure_submissions" in f.read_text(errors="ignore")]
    assert writers == []


def test_a_release_request_is_refused_and_a_pending_one_can_only_be_closed(api):
    maker = _login(api, "admin@meridian.demo", "Demo!admin1")
    checker = _login(api, "approver@meridian.demo", "Demo!approve1")
    r = api.post("/v1/approvals", headers=maker, json={"request_type": "submission.release", "payload": {}})
    assert r.status_code == 410 and "filing lifecycle" in r.text

    s = api.s
    mk = s.execute(text("SELECT user_id FROM users WHERE email = 'admin@meridian.demo'")).scalar()
    rid = s.execute(text("""INSERT INTO approval_requests (org_id, request_type, title, payload, maker_user_id)
                            VALUES (CAST(:o AS uuid), 'submission.release', 'legacy', '{}'::jsonb, :m) RETURNING request_id::text"""),
                    {"o": BANK_ORG, "m": mk}).scalar()
    sub = s.execute(text("""INSERT INTO bank_disclosure_submissions (org_id, framework, period_label, period_start, period_end,
                                scenario, horizon, snapshot, maker_user_id, approval_request_id)
                            VALUES (CAST(:o AS uuid), 'TEST_RETIRED', 'Q9 2099', '2099-07-01', '2099-09-30', 'baseline',
                                    'current', CAST(:snap AS jsonb), :m, CAST(:r AS uuid)) RETURNING submission_id::text"""),
                    {"o": BANK_ORG, "snap": json.dumps({"rollup": {}}), "m": mk, "r": rid}).scalar()

    r = api.post(f"/v1/approvals/{rid}/decide", headers=checker, json={"decision": "approved"})
    assert r.status_code == 410 and "Reject this request" in r.text
    status = lambda q: s.execute(text(q), {"x": sub if "submission" in q else rid}).scalar()   # noqa: E731
    assert status("SELECT status FROM bank_disclosure_submissions WHERE submission_id = CAST(:x AS uuid)") == "draft"
    assert status("SELECT status FROM approval_requests WHERE request_id = CAST(:x AS uuid)") == "pending"

    r = api.post(f"/v1/approvals/{rid}/decide", headers=checker, json={"decision": "rejected", "reason": "retired"})
    assert r.status_code == 200, r.text
    assert status("SELECT status FROM bank_disclosure_submissions WHERE submission_id = CAST(:x AS uuid)") == "rejected"
