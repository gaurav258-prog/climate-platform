"""Finish the demo banks' Pillar 3 Template 1 for a walkthrough — DEMO data for the fictional demo banks only (run after
scripts/seed_demo_counterparties.py):

  demo seed correction   loans the demo seed gave the same name and no asset id get a demo asset id (DEMO-<bank>-<n>),
                         so they can be matched like any loan; and, per bank, six loans whose counterparty states a revenue
                         and whose NACE division has a demo intensity no longer carry a gathered scope 3 (the counterparty
                         'did not report it') — so the revenue-based sector average is used for them. Written as the demo
                         seed scripts write (the app has no path to correct the seed's own data).
  through the app        those loans' counterparties (attributes file, by asset id; counterparties file, four eyes where
                         asked), and the Template 1 narrative — demo text, through the qualitative tables route

Idempotent. Local demo only.

  venv/bin/python scripts/seed_demo_t1_showcase.py [--base http://localhost:8001]
"""
from __future__ import annotations

import argparse
import random
import sys

import httpx
from sqlalchemy import text

from scripts.seed_demo_counterparties import (
    BANKS,
    PERIOD_END,
    SECTION_INTENSITY,
    _approve,
    _csv,
    _division,
    _login,
)

N_SECTOR_AVERAGE = 6
NARRATIVE = {
    "t1.data_sources": "[Demo text] Counterparties' scope 1, 2 and 3 emissions are taken from their own sustainability "
                       "reports where they publish them; where a counterparty reports no scope 3, the bank uses a sector-"
                       "average intensity per EUR million of revenue for its NACE division (demo source, 2024 vintage).",
    "t1.methodology": "[Demo text] Each counterparty's emissions are attributed to the exposure by the exposure's gross "
                      "carrying amount compared to the counterparty's total liabilities and equity, as Annex XL column i "
                      "describes. A missing scope 3 is estimated as the division's intensity multiplied by the "
                      "counterparty's revenue for its financial year ending on or before the reference date.",
    "t1.emission_kinds": "[Demo text] The bank discloses (a) emissions reported by the counterparties and (c) economic "
                         "activity-based emissions (the revenue-based sector averages); it does not use physical "
                         "activity-based emissions.",
}


def _session():
    from core.db.config import SessionLocal
    return SessionLocal()


def _demo_asset_ids(org: str, code: str) -> list[dict]:
    """Loans sharing a name and lacking an asset id get one (demo seed correction); returns the loans that need a
    counterparty."""
    with _session() as s:
        rows = s.execute(text("""
            SELECT e.entity_id::text AS id, e.entity_name AS name, e.external_ref AS ref, e.borrower_entity_id AS cp,
                   CAST(x.outstanding_loan_balance_eur AS FLOAT) AS ob, CAST(x.annual_revenue_eur AS FLOAT) AS rev
            FROM portfolio_entities e JOIN ext_banking x USING (entity_id) JOIN organizations o ON o.org_id = e.org_id
            WHERE o.name = :n AND e.vertical = 'banking' AND e.source = 'own'
              AND e.entity_name IN (SELECT e2.entity_name FROM portfolio_entities e2 WHERE e2.org_id = e.org_id
                                    AND e2.vertical = 'banking' AND e2.source = 'own' GROUP BY 1 HAVING count(*) > 1)
            ORDER BY e.entity_name, e.entity_id"""), {"n": org}).mappings().all()
        out = []
        for k, r in enumerate(rows, 1):
            ref = r["ref"] or f"DEMO-{code}-{k:03d}"
            if not r["ref"]:
                s.execute(text("UPDATE portfolio_entities SET external_ref = :r, updated_at = now() WHERE entity_id = CAST(:i AS uuid)"),
                          {"r": ref, "i": r["id"]})
            out.append({**dict(r), "ref": ref})
        s.commit()
    return [r for r in out if not r["cp"]]


def _unreport_scope3(org: str, code: str) -> int:
    """Six loans per bank lose their gathered scope 3 (demo seed correction) — those whose counterparty states a revenue
    and whose division has a demo intensity; already done if six such loans exist."""
    with _session() as s:
        cands = s.execute(text("""
            SELECT e.entity_id::text AS id, e.nace_code AS nace, x.ghg_emissions_scope3_tco2e IS NULL AS done
            FROM portfolio_entities e JOIN ext_banking x USING (entity_id) JOIN organizations o ON o.org_id = e.org_id
            JOIN bank_counterparties c ON c.org_id = e.org_id AND c.counterparty_ref = e.borrower_entity_id
            WHERE o.name = :n AND e.vertical = 'banking' AND e.source = 'own' AND c.revenue_eur IS NOT NULL
              AND x.ghg_emissions_scope1_tco2e IS NOT NULL AND x.ghg_emissions_scope2_tco2e IS NOT NULL
            ORDER BY e.entity_name, e.entity_id"""), {"n": org}).mappings().all()
        ok = [c for c in cands if (_division(c["nace"]) or " ")[0] in SECTION_INTENSITY]
        have = sum(1 for c in ok if c["done"])
        pick = [c for c in random.Random(code).sample(ok, min(len(ok), 3 * N_SECTOR_AVERAGE)) if not c["done"]]
        pick = pick[:max(0, N_SECTOR_AVERAGE - have)]
        for c in pick:
            s.execute(text("UPDATE ext_banking SET ghg_emissions_scope3_tco2e = NULL WHERE entity_id = CAST(:i AS uuid)"),
                      {"i": c["id"]})
        s.commit()
    return have + len(pick)


def showcase(c: httpx.Client, slug: str, org: str) -> str:
    maker = _login(c, f"analyst@{slug}.demo", "Demo!analyst1")
    checker = (_login(c, "approver@meridian.demo", "Demo!approve1") if slug == "meridian"
               else _login(c, f"admin@{slug}.demo", "Demo!admin1"))
    code = slug.upper()[:8]
    rng = random.Random(f"{slug}-dup")
    loans = _demo_asset_ids(org, code)
    if loans:
        rows = [[ln["ref"], f"{code}-CP-D{k:03d}", ""] for k, ln in enumerate(loans, 1)]
        r = c.post("/v1/bank/assets/attributes/upload", headers=maker, data={"currency": "EUR", "book_date": PERIOD_END},
                   files={"file": ("demo-attributes-ids.csv", _csv(["external_ref", "borrower_entity_id", "emissions_company_reported"],
                                                                   [[a, b, "true"] for a, b, _ in rows]), "text/csv")})
        if r.status_code != 200 or r.json()["n_updated"] != len(rows):
            raise SystemExit(f"{slug} attributes by id: {r.status_code} {r.text[:300]}")
        cps = []
        for (_, cp, _), ln in zip(rows, loans):
            liabilities = round((ln["ob"] or 1_000_000.0) * rng.uniform(4, 20), 2)
            cps.append([cp, f"{ln['name']} (demo)", liabilities, ln["rev"] or round(liabilities * rng.uniform(0.3, 1.2), 2),
                        "EUR", PERIOD_END])
        r = c.post("/v1/bank/counterparties/upload", headers=maker,
                   files={"file": ("demo-counterparties-ids.csv", _csv(["counterparty_ref", "counterparty_name",
                                                                        "total_liabilities_eur", "counterparty_revenue_eur",
                                                                        "currency", "book_date"], cps), "text/csv")},
                   data={"currency": "EUR", "book_date": PERIOD_END, "approval_reason": "demo counterparties"})
        if r.status_code not in (200, 202):
            raise SystemExit(f"{slug} counterparties: {r.status_code} {r.text[:300]}")
        if r.status_code == 202:
            _approve(c, checker, r.json()["approval_request_id"], "demo counterparties checked")
    n_sa = _unreport_scope3(org, code)
    r = c.patch("/v1/filings/qualitative/p3esg", headers=maker, json={"values": NARRATIVE})
    if r.status_code != 200:
        raise SystemExit(f"{slug} narrative: {r.status_code} {r.text[:300]}")
    return f"{slug}: {len(loans)} loans given an asset id and a counterparty, {n_sa} on the sector average, narrative written"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8001")
    a = ap.parse_args()
    if not a.base.startswith(("http://localhost", "http://127.0.0.1")):
        print("demo seeding runs against a local development API only", file=sys.stderr)
        return 2
    with httpx.Client(base_url=a.base, timeout=120) as c:
        for slug, org in BANKS.items():
            print(showcase(c, slug, org))
    return 0


if __name__ == "__main__":
    sys.exit(main())
