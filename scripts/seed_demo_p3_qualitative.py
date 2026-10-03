"""The eight demo banks answer Pillar 3 ESG qualitative Tables 1-3 (environmental, social, governance risk) — DEMO text for
the fictional demo banks, marked '[Demo text]', for the organisation and its reporting period end, through the app's
qualitative tables route (audited like any author's text). Not a real institution's disclosure.

A row already answered is left as it is. Local demo only.

  venv/bin/python scripts/seed_demo_p3_qualitative.py [--base http://localhost:8001]
"""
from __future__ import annotations

import argparse
import sys

import httpx

from scripts.seed_demo_counterparties import BANKS, _login


def _text(bank: str, table: str, group: str, prompt: str) -> str:
    topic = {"TAB1": "environmental", "TAB2": "social", "TAB3": "governance"}[table]
    return (f"[Demo text] {bank} — {prompt.rstrip('.')}: set out in the bank's {topic} risk framework, approved by its "
            f"management body and reviewed yearly ({group or 'general'}). Illustrative demo answer; not a real "
            "institution's disclosure.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8001")
    a = ap.parse_args()
    if not a.base.startswith(("http://localhost", "http://127.0.0.1")):
        print("demo seeding runs against a local development API only", file=sys.stderr)
        return 2
    with httpx.Client(base_url=a.base, timeout=120) as c:
        for slug, org in BANKS.items():
            h = _login(c, f"analyst@{slug}.demo", "Demo!analyst1")
            q = c.get("/v1/filings/qualitative/p3esg", headers=h).json()
            bank = org.removesuffix(" (demo)")
            values = {r["key"]: _text(bank, t["table"], r.get("group") or "", r["prompt"])
                      for t in q["tables"] if t["table"].startswith("TAB") for r in t["rows"] if not r["value"].strip()}
            if values:
                r = c.patch("/v1/filings/qualitative/p3esg", headers=h, json={"values": values})
                if r.status_code != 200:
                    print(f"{slug}: {r.status_code} {r.text[:300]}", file=sys.stderr)
                    return 1
            print(f"{slug}: {len(values)} rows answered (period {q['period_end']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
