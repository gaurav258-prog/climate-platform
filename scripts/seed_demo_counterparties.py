"""The eight demo banks name their loans' counterparties and state what Pillar 3 Template 1 columns i-k read — DEMO
figures, made up for the fictional demo banks (not regulatory, not validated, no real company), through the app's own
governed paths, four eyes where the app asks for them:

  attributes file      each loan's counterparty id (Counterparty ID (LEI)); about one loan in five shares its
                       counterparty with the next, so 'one counterparty, one figure' shows; whether the loan's emissions
                       are the company's own reporting (column k) — true where it states scopes 1 and 2
  counterparties file  each counterparty once: total liabilities and equity, revenue (the loan's demo revenue where it
                       has one), the financial year end 2025-12-31
  methodology          Template 1 statements: scopes 1-3 estimated, attributed by exposure over total liabilities, the
                       sector average per EUR million of revenue — and a demo intensity per NACE division in the books

Idempotent: a loan that already names a counterparty keeps it; a value already attested for the year is left as it is.

  venv/bin/python scripts/seed_demo_counterparties.py [--base http://localhost:8001]

Local demo only: logs in with the seeded demo credentials (scripts/seed_demo_population.py, scripts/seed_auth_demo.py).
"""
from __future__ import annotations

import argparse
import csv
import io
import random
import sys

import httpx
from sqlalchemy import text

BANKS = {"meridian": "Meridian Bank (demo)", "tejo": "Banco do Tejo (demo)", "atlantique": "Banque Atlantique (demo)",
         "levante": "Caja Levante (demo)", "hibernia": "Hibernia Bank (demo)", "lombardia": "Lombardia Credito (demo)",
         "nordsee": "Nordsee Sparkasse (demo)", "rheinmain": "Rhein-Main Kreditbank (demo)"}
PERIOD_END = "2025-12-31"
PROVIDER = "Demo seed: illustrative sector averages (not a published source, not regulatory)"
# demo scope 3 intensity, tCO2e per EUR million of revenue, by NACE section of the division — illustrative only
SECTION_INTENSITY = {"A": 900.0, "B": 1500.0, "C": 600.0, "D": 1200.0, "E": 800.0, "F": 450.0, "G": 300.0, "H": 700.0,
                     "I": 250.0, "J": 120.0, "K": 80.0, "L": 150.0, "M": 150.0, "N": 200.0}
STATEMENTS = {"p3esg_t1_emissions_estimation": "scope_1_2_3", "p3esg_t1_attribution": "exposure_over_total_liabilities",
              "p3esg_t1_scope3_sector_average": "intensity_x_revenue"}


def _login(c: httpx.Client, email: str, pw: str) -> dict:
    r = c.post("/v1/auth/login", json={"email": email, "password": pw})
    r.raise_for_status()
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def _csv(header: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode()


def _approve(c, checker, rid, why):
    d = c.post(f"/v1/approvals/{rid}/decide", headers=checker, json={"decision": "approved", "reason": why})
    if d.status_code != 200:
        raise SystemExit(f"approve {rid}: {d.status_code} {d.text[:200]}")


def _loans(org: str) -> list[dict]:
    """The bank's loans as held (read only): name, counterparty id, balance, the loan's demo revenue, NACE, emissions."""
    from core.db.config import SessionLocal
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text("""
            SELECT e.entity_name AS name, e.borrower_entity_id AS cp, e.nace_code AS nace,
                   CAST(x.outstanding_loan_balance_eur AS FLOAT) AS ob, CAST(x.annual_revenue_eur AS FLOAT) AS rev,
                   x.ghg_emissions_scope1_tco2e IS NOT NULL AND x.ghg_emissions_scope2_tco2e IS NOT NULL AS s12
            FROM portfolio_entities e JOIN ext_banking x USING (entity_id) JOIN organizations o ON o.org_id = e.org_id
            WHERE o.name = :n AND e.vertical = 'banking' AND e.source = 'own'
            ORDER BY e.entity_name"""), {"n": org}).mappings().all()]


def _division(nace: str | None) -> str | None:
    from services.reference import nace as N
    return N.division(nace)


def seed_bank(c: httpx.Client, slug: str, org: str) -> str:
    maker = _login(c, f"analyst@{slug}.demo", "Demo!analyst1")
    checker = (_login(c, "approver@meridian.demo", "Demo!approve1") if slug == "meridian"
               else _login(c, f"admin@{slug}.demo", "Demo!admin1"))
    loans = _loans(org)
    counts: dict[str, int] = {}
    for ln in loans:
        counts[ln["name"]] = counts.get(ln["name"], 0) + 1
    rng = random.Random(slug)
    code = slug.upper()[:8]

    # ── 1 each loan's counterparty (a name shared by two loans cannot be matched by name: left, reported) ──
    attrs, groups, n, i = [], {}, 0, 0
    while i < len(loans):
        n += 1
        pair = loans[i:i + 2] if i % 5 == 0 and i + 1 < len(loans) else loans[i:i + 1]
        cp = pair[0]["cp"] or f"{code}-CP-{n:04d}"
        for ln in pair:
            if counts[ln["name"]] != 1:
                continue
            groups.setdefault(ln["cp"] or cp, []).append(ln)
            row = [ln["name"], "" if ln["cp"] else cp, "true" if ln["s12"] else ""]
            attrs.append(row)
        i += len(pair)
    r = c.post("/v1/bank/assets/attributes/upload", headers=maker, data={"currency": "EUR", "book_date": PERIOD_END},
               files={"file": ("demo-attributes.csv", _csv(["asset_name", "borrower_entity_id", "emissions_company_reported"],
                                                           attrs), "text/csv")})
    if r.status_code != 200:
        raise SystemExit(f"{slug} attributes: {r.status_code} {r.text[:300]}")
    att = r.json()

    # ── 2 each counterparty once: total liabilities and equity (well above what the bank lends it), revenue ──
    rows = []
    for cp, members in sorted(groups.items()):
        lent = sum(m["ob"] or 0 for m in members) or 1_000_000.0
        liabilities = round(lent * rng.uniform(4, 20), 2)
        revenue = next((m["rev"] for m in members if m["rev"]), None) or round(liabilities * rng.uniform(0.3, 1.2), 2)
        rows.append([cp, f"{members[0]['name']} (demo)", liabilities, revenue, "EUR", PERIOD_END])
    r = c.post("/v1/bank/counterparties/upload", headers=maker,
               files={"file": ("demo-counterparties.csv", _csv(["counterparty_ref", "counterparty_name", "total_liabilities_eur",
                                                                 "counterparty_revenue_eur", "currency", "book_date"], rows),
                               "text/csv")},
               data={"currency": "EUR", "book_date": PERIOD_END, "approval_reason": "demo counterparties"})
    if r.status_code not in (200, 202):
        raise SystemExit(f"{slug} counterparties: {r.status_code} {r.text[:300]}")
    if r.status_code == 202:
        _approve(c, checker, r.json()["approval_request_id"], "demo counterparties checked")

    # ── 3 the Template 1 statements, and a demo revenue intensity per division in the books ──
    # a method statement is configuration: the admin states it; the other person approves where the bank requires it
    admin = _login(c, f"admin@{slug}.demo", "Demo!admin1")
    second = checker if slug == "meridian" else maker
    r = c.patch("/v1/calc-settings", headers=admin, json={"interpretation": STATEMENTS})
    if r.status_code != 200:
        raise SystemExit(f"{slug} statements: {r.status_code} {r.text[:300]}")
    if r.json().get("status") == "pending_approval":
        _approve(c, second, r.json()["request_id"], "demo Template 1 statements")
    have = {p.get("breakdown_member") for p in c.get("/v1/provided?framework=method", headers=maker).json()["provided"]
            if p["datapoint_key"] == "method.t1_sector_scope3_intensity_revenue" and p["status"] == "attested"
            and p["reporting_period_end"] == PERIOD_END}
    stated = 0
    for d in sorted({_division(ln["nace"]) for ln in loans} - {None} - have):
        v = SECTION_INTENSITY.get(d[0])
        if v is None:
            continue
        r = c.post("/v1/provided", headers=maker, json={
            "framework": "method", "datapoint_key": "method.t1_sector_scope3_intensity_revenue", "value_num": v,
            "breakdown_member": d, "source": "client", "provider_name": PROVIDER, "data_vintage": "2024-12-31",
            "reporting_period_end": PERIOD_END})
        if r.status_code != 201:
            raise SystemExit(f"{slug} intensity {d}: {r.status_code} {r.text[:300]}")
        _approve(c, checker, r.json()["approval_request_id"], "demo sector average checked")
        stated += 1
    skipped = sum(1 for k, v in counts.items() if v > 1)
    return (f"{slug}: {att['n_updated']} loans updated ({att['n_refused']} refused, {skipped} shared names left), "
            f"{len(rows)} counterparties stated, {stated} division intensities attested")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8001")
    a = ap.parse_args()
    if not a.base.startswith(("http://localhost", "http://127.0.0.1")):
        print("demo seeding runs against a local development API only", file=sys.stderr)
        return 2
    with httpx.Client(base_url=a.base, timeout=120) as c:
        for slug, org in BANKS.items():
            print(seed_bank(c, slug, org))
    return 0


if __name__ == "__main__":
    sys.exit(main())
