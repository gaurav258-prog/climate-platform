"""Withdraw the demo organisations' unfiled drafts of RETIRED report types — DEMO cleanup for fictional demo companies
only. A filing of a retired type (services.governance.filings.FRAMEWORKS 'retired') can never be submitted; one still
in draft or in review only clutters the register. Through the app's own lifecycle:

  in review   a second person returns it (POST /v1/approvals/{id}/decide, decision 'returned') — needs the filing's
              four-eyes request; a filing put in review without one (the demo seed set the status directly) is
              reported and left, unless --raise-missing-review: the maker then raises the filing's review request
              (POST /v1/approvals, 'filing.approve') so the second person can return it
  draft       the maker withdraws it (POST /v1/filings/{id}/withdraw, with the reason)

Submitted and accepted filings are never touched. Idempotent: a filing already withdrawn is no longer listed.

  venv/bin/python scripts/withdraw_retired_demo_drafts.py [--base http://localhost:8001] [--raise-missing-review]

Local demo only: logs in with the seeded demo credentials (scripts/seed_demo_population.py, scripts/seed_auth_demo.py).
"""
from __future__ import annotations

import argparse
import sys

import httpx
from sqlalchemy import text

from scripts.seed_demo_insurers_entities import login

REASON = "Retired report type — this draft can never be filed (demo cleanup)."
APPROVERS = {"meridian", "iberia", "stellar", "nordkap", "terra"}


def _unfiled() -> list[dict]:
    """The demo organisations' draft / in-review / returned filings of a retired type, with the org's login slug."""
    from core.db.config import SessionLocal
    from services.governance.filings import FRAMEWORKS
    retired = [k for k, v in FRAMEWORKS.items() if v.get("retired")]
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text("""
            SELECT f.filing_id::text AS id, f.framework, f.status, o.name AS org,
                   f.approval_request_id::text AS rid,
                   (SELECT split_part(split_part(min(u.email), '@', 2), '.demo', 1) FROM users u
                    WHERE u.org_id = o.org_id AND u.email LIKE 'analyst@%.demo') AS slug
            FROM regulatory_filing f JOIN organizations o ON o.org_id = f.org_id
            WHERE o.name LIKE '%(demo)%' AND f.framework = ANY(:fw) AND f.status IN ('draft', 'in_review', 'returned')
            ORDER BY o.name, f.framework"""), {"fw": retired}).mappings().all()]


def withdraw_one(c: httpx.Client, f: dict, users: dict, raise_missing: bool) -> str:
    slug = f["slug"]
    if slug not in users:
        users[slug] = (login(c, f"analyst@{slug}.demo", "Demo!analyst1"),
                       login(c, f"approver@{slug}.demo", "Demo!approve1") if slug in APPROVERS
                       else login(c, f"admin@{slug}.demo", "Demo!admin1"))
    maker, checker = users[slug]
    head = f"{f['id']} {f['framework']} [{f['org']}]"
    if f["status"] == "in_review":
        rid = f["rid"]
        if not rid:
            if not raise_missing:
                return f"{head}: LEFT — in review with no four-eyes request to return (the seed set the status directly)"
            r = c.post("/v1/approvals", headers=maker, json={
                "request_type": "filing.approve", "title": f"Approve {f['framework']} (retired — to be returned)",
                "payload": {"filing_id": f["id"], "framework": f["framework"]}})
            if r.status_code != 201:
                return f"{head}: LEFT — raising its review request refused: {r.status_code} {r.text[:300]}"
            rid = r.json()["id"]
        d = c.post(f"/v1/approvals/{rid}/decide", headers=checker, json={"decision": "returned", "reason": REASON})
        if d.status_code != 200:
            return f"{head}: LEFT — return refused: {d.status_code} {d.text[:300]}"
    w = c.post(f"/v1/filings/{f['id']}/withdraw", headers=maker, json={"reason": REASON})
    if w.status_code != 200:
        return f"{head}: LEFT — withdraw refused: {w.status_code} {w.text[:300]}"
    return f"{head}: {f['status']} -> {w.json().get('status')}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8001")
    ap.add_argument("--raise-missing-review", action="store_true")
    a = ap.parse_args()
    if not a.base.startswith(("http://localhost", "http://127.0.0.1")):
        print("demo cleanup runs against a local development API only", file=sys.stderr)
        return 2
    users: dict = {}
    with httpx.Client(base_url=a.base, timeout=120) as c:
        rows = _unfiled()
        print(f"{len(rows)} unfiled filings of retired report types in demo organisations")
        for f in rows:
            print(withdraw_one(c, f, users, a.raise_missing_review))
    return 0


if __name__ == "__main__":
    sys.exit(main())
