"""Nordkap Asset Management (demo) holds only fictional demo companies — DEMO cleanup. Its funds held real listed
companies (Nestlé, SAP, Apple, …) with emissions and ESG figures the demo seed had made up for them; the platform never
carries invented data for a real named company. Through the app's own routes:

  holdings     each Nordkap fund, on each date it holds positions, gets a COMPLETE book (POST /v1/funds/{id}/holdings,
               complete_book, E145) of the four fictional demo issuers (DE00ENERGY01, ES00FOODS001, NL00LOGIS001,
               SE00SOFT0001) at the date's book value, with their demo PAI and Taxonomy facts — the real companies'
               positions on that date are removed (audited)
  issuer data  Nordkap's own figures about every real company are withdrawn (POST /v1/issuers/{id}/client-data/withdraw,
               E146; kept in the audit record with the reason) — the shared reference (GLEIF identity) is untouched
  filing       a Nordkap filing in review or draft that froze the old book is returned (four eyes) and withdrawn, so a
               new one is prepared from the fictional book (POST /v1/filings/{id}/withdraw)

Idempotent: a date already holding exactly the demo book is uploaded again unchanged; nothing left to withdraw is skipped.

  PYTHONPATH=. venv/bin/python scripts/seed_demo_nordkap_fictional.py [--base http://localhost:8001]

Local demo only: logs in with the seeded demo credentials (scripts/seed_demo_population.py, scripts/seed_auth_demo.py).
"""
from __future__ import annotations

import argparse
import sys

import httpx
from sqlalchemy import text

from scripts.seed_demo_asset_managers import _TAX_FIELDS, FLAGS, ISSUERS, TAXONOMY, _login, _ok
from scripts.withdraw_retired_demo_drafts import withdraw_one

ORG = "Nordkap Asset Management (demo)"
WEIGHTS = {"ES00FOODS001": 0.35, "SE00SOFT0001": 0.25, "NL00LOGIS001": 0.20, "DE00ENERGY01": 0.20}
REASON = ("Demo data made up for a real listed company — the demo holds fictional companies only; replaced by the "
          "fictional demo book (demo cleanup).")


def _read(sql: str, **params) -> list[dict]:
    from core.db.config import SessionLocal
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text(sql), params).mappings().all()]


def books() -> list[dict]:
    """Each Nordkap fund's dates and the book value on each (read only)."""
    return _read("""
        SELECT f.fund_id::text AS fund_id, f.name, p.as_of_date::text AS d, CAST(sum(p.market_value_eur) AS FLOAT) AS value
        FROM funds f JOIN organizations o ON o.org_id = f.org_id JOIN fund_positions p ON p.fund_id = f.fund_id
        WHERE o.name = :n GROUP BY 1, 2, 3 ORDER BY 2, 3""", n=ORG)


def real_issuers_with_our_data() -> list[dict]:
    """Issuers Nordkap holds data of its own about that are not the fictional demo issuers (read only, through
    services.issuer_client_data — the stores' own readers)."""
    from core.db.config import SessionLocal
    from services.issuer_client_data import issuers_with_own_data
    with SessionLocal() as s:
        org_id = s.execute(text("SELECT org_id::text FROM organizations WHERE name = :n"), {"n": ORG}).scalar()
        return [i for i in issuers_with_own_data(s, org_id) if not (i["lei"] or "").startswith("DEMO")]


def open_filings() -> list[dict]:
    return _read("""
        SELECT f.filing_id::text AS id, f.framework, f.status, o.name AS org, f.approval_request_id::text AS rid,
               'nordkap' AS slug
        FROM regulatory_filing f JOIN organizations o ON o.org_id = f.org_id
        WHERE o.name = :n AND f.status IN ('draft', 'in_review', 'returned') ORDER BY f.framework""", n=ORG)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8001")
    a = ap.parse_args()
    if not a.base.startswith(("http://localhost", "http://127.0.0.1")):
        print("demo seeding runs against a local development API only", file=sys.stderr)
        return 2
    with httpx.Client(base_url=a.base, timeout=300) as c:
        maker = _login(c, "analyst@nordkap.demo", "Demo!analyst1")
        for b in books():
            holdings = [{"isin": isin, "market_value_eur": round(b["value"] * w, 2), "asset_class": "equity",
                         "reporting_year": 2024, **ISSUERS[isin], **FLAGS, **dict(zip(_TAX_FIELDS, TAXONOMY[isin]))}
                        for isin, w in WEIGHTS.items()]
            r = _ok(c.post(f"/v1/funds/{b['fund_id']}/holdings", headers=maker,
                           json={"as_of_date": b["d"], "holdings": holdings, "complete_book": True}),
                    f"{b['name']} {b['d']}")
            print(f"{b['name']} {b['d']}: {r['positions_created']} demo positions; "
                  f"{len(r['positions_removed'])} real-company positions removed")
        for i in real_issuers_with_our_data():
            r = _ok(c.post(f"/v1/issuers/{i['issuer_id']}/client-data/withdraw", headers=maker, json={"reason": REASON}),
                    f"withdraw {i['name']}")
            print(f"{i['name']}: withdrawn {r['withdrawn']}")
        users: dict = {}
        for f in open_filings():
            print(withdraw_one(c, f, users, True, REASON))
    return 0


if __name__ == "__main__":
    sys.exit(main())
