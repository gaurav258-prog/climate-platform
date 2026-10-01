"""Demo companies state their methods (provided values of family 'method') through the app, four eyes on each value.

The values are data/demo/method_statements.json: the platform's own values before commit 3e8f518 (E69), each with its
source line — stated by DEMO companies only, as their method; not regulatory, not validated. A real customer states its
own in Admin → Methodology. Idempotent: a value already attested for that company and year is left as it is.

  venv/bin/python scripts/seed_demo_methods.py [--base http://localhost:8001] [--period-end 2025-12-31]

Local demo only: logs in with the seeded demo credentials (scripts/seed_auth_demo.py)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
# one demo company per sector, each with a maker and a second person to attest (scripts/seed_auth_demo.py)
COMPANIES = ("meridian", "iberia", "stellar", "nordkap", "terra")
PROVIDER = "Demo seed: the platform's values before E69 (not regulatory, not validated)"


def _login(c: httpx.Client, email: str, pw: str) -> dict:
    r = c.post("/v1/auth/login", json={"email": email, "password": pw})
    r.raise_for_status()
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8001")
    ap.add_argument("--period-end", default="2025-12-31")
    a = ap.parse_args()
    if not a.base.startswith(("http://localhost", "http://127.0.0.1")):
        print("demo seeding runs against a local development API only", file=sys.stderr)
        return 2
    values = json.loads((ROOT / "data" / "demo" / "method_statements.json").read_text())["values"]
    with httpx.Client(base_url=a.base, timeout=60) as c:
        for co in COMPANIES:
            maker = _login(c, f"analyst@{co}.demo", "Demo!analyst1")
            checker = _login(c, f"approver@{co}.demo", "Demo!approve1")
            have = {(p["datapoint_key"], p.get("breakdown_member")) for p in
                    c.get("/v1/provided?framework=method", headers=maker).json()["provided"]
                    if p["status"] == "attested" and p["reporting_period_end"] == a.period_end}
            n = 0
            for v in values:
                if (v["key"], v["member"]) in have:
                    continue
                r = c.post("/v1/provided", headers=maker, json={
                    "framework": "method", "datapoint_key": v["key"], "value_num": v["value"], "source": "client",
                    "provider_name": PROVIDER, "reporting_period_end": a.period_end,
                    **({"breakdown_member": v["member"]} if v["member"] else {})})
                if r.status_code != 201:
                    print(f"{co} {v['key']} {v['member']}: {r.status_code} {r.text[:200]}", file=sys.stderr)
                    return 1
                d = c.post(f"/v1/approvals/{r.json()['approval_request_id']}/decide", headers=checker,
                           json={"decision": "approved", "reason": "demo method statement checked against its source line"})
                if d.status_code != 200:
                    print(f"{co} approve {v['key']}: {d.status_code} {d.text[:200]}", file=sys.stderr)
                    return 1
                n += 1
            print(f"{co}: {n} stated and attested ({len(have)} already)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
