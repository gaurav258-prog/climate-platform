"""The demo insurers state their Solvency II capital and reinsurance in force, and the demo banks' legal entities author
their Pillar 3 qualitative text — DEMO data, made up for fictional demo companies (not regulatory, not validated, no
real undertaking or institution), through the app's own governed paths:

  insurers   for every undertaking an open Solvency II obligation names (the organisation as a whole, or a legal
             entity / group), the 'insurer_solvency' provided values for the reporting period: eligible own funds, SCR,
             MCR (own funds above the SCR, MCR below it) and the reinsurance programme (quota share, cat excess of
             loss attachment / limit, one reinstatement and its premium) — POST /v1/provided by the analyst, attested
             by a second person (POST /v1/approvals/{id}/decide)
  banks      for every legal entity an open Pillar 3 obligation names, the Template 1 narrative (data sources,
             methodology, emission kinds) and every Tables 1-3 row, marked '[Demo text]', for that institution and
             reference date — PATCH /v1/filings/qualitative/p3esg

Afterwards it runs the preflight of every open obligation of these organisations and prints what still shows as a gap.

Idempotent: a value already attested for the undertaking and period, or a row already answered, is left as it is.

  venv/bin/python scripts/seed_demo_insurers_entities.py [--base http://localhost:8001]

Local demo only: logs in with the seeded demo credentials (scripts/seed_demo_population.py, scripts/seed_auth_demo.py).
"""
from __future__ import annotations

import argparse
import random
import sys
import time

import httpx

PERIOD_END = "2025-12-31"
INSURERS = {"adriatica": "Adriatica Assicurazioni (demo)", "alpenrueck": "Alpenrück Versicherung (demo)",
            "rhone": "Assurances du Rhône (demo)", "delta": "Delta Verzekeringen (demo)", "iberia": "Iberia Mutual (demo)",
            "lusitania": "Lusitânia Seguros (demo)", "nordlys": "Nordlys Forsikring (demo)"}
BANKS = {"meridian": "Meridian Bank (demo)", "hibernia": "Hibernia Bank (demo)"}
APPROVERS = {"meridian", "iberia", "stellar", "nordkap", "terra"}     # core demo orgs with an approver user
SOLVENCY = ("insurer_solvency", "insurer_orsa_climate", "insurer_recovery_stress")
PROVIDER = {"capital": "Demo seed: illustrative Solvency II return (not a real undertaking's figures)",
            "treaty": "Demo seed: illustrative reinsurance treaty (not a real programme)"}
DONE = ("submitted", "accepted")
T1_NARRATIVE = ("t1.data_sources", "t1.methodology", "t1.emission_kinds")


def login(c: httpx.Client, email: str, pw: str) -> dict:
    """One login per user (the login is rate limited: on 429 wait and retry)."""
    for wait in (20, 40, 60, 60):
        r = c.post("/v1/auth/login", json={"email": email, "password": pw})
        if r.status_code == 429:
            time.sleep(wait)
            continue
        r.raise_for_status()
        return {"Authorization": "Bearer " + r.json()["access_token"]}
    raise SystemExit(f"login {email}: still rate limited")


def pair(c: httpx.Client, slug: str) -> tuple[dict, dict]:
    """(maker, checker): the analyst, and the approver (core demo orgs) or the admin as the second person."""
    maker = login(c, f"analyst@{slug}.demo", "Demo!analyst1")
    checker = (login(c, f"approver@{slug}.demo", "Demo!approve1") if slug in APPROVERS
               else login(c, f"admin@{slug}.demo", "Demo!admin1"))
    return maker, checker


def open_obligations(c: httpx.Client, h: dict) -> list[dict]:
    r = c.get("/v1/obligations", headers=h)
    r.raise_for_status()
    return [o for o in r.json()["obligations"] if not o.get("retired") and o.get("filing_status") not in DONE]


def preflight_gaps(c: httpx.Client, h: dict, ob: dict) -> list[str]:
    q = {"framework": ob["framework"], **{k: ob[k] for k in ("entity_id", "fund_id") if ob.get(k)}}
    r = c.get("/v1/filings/preflight", headers=h, params=q)
    if r.status_code != 200:
        return [f"preflight refused ({r.status_code}): {r.text[:200]}"]
    return r.json().get("gaps") or []


# ── insurers ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def demo_figures(slug: str, scope: str | None, share: float) -> dict:
    """Plausible demo Solvency II figures for one undertaking (EUR, deterministic per company and scope): own funds
    150-230 % of the SCR, MCR 30-42 % of it; a quota share, and a cat layer sized to the SCR."""
    rng = random.Random(f"{slug}:{scope or 'organisation'}")
    scr = round(rng.uniform(180e6, 620e6) * share, -5)
    limit = round(scr * rng.uniform(0.8, 1.4), -5)
    return {"scr_total": scr, "eligible_own_funds_scr": round(scr * rng.uniform(1.5, 2.3), -5),
            "mcr_total": round(scr * rng.uniform(0.30, 0.42), -5),
            "ri_quota_share_pct": float(rng.choice((10, 15, 20, 25, 30))),
            "ri_xol_attachment_eur": round(scr * rng.uniform(0.15, 0.3), -5), "ri_xol_limit_eur": limit,
            "ri_xol_reinstatements": 1.0, "ri_xol_reinstatement_premium_eur": round(limit * rng.uniform(0.05, 0.1), -4)}


def _scopes(c: httpx.Client, h: dict) -> dict[str | None, float]:
    """{undertaking: size share}: every undertaking an open Solvency II obligation names (None = the organisation). A
    legal entity under a group carries part of the group's size; the group and the organisation the whole."""
    ents = {e["entity_id"]: e for e in c.get("/v1/filings/entities", headers=h).json().get("entities", [])}
    named = {o.get("entity_id") for o in open_obligations(c, h) if o["framework"] in SOLVENCY}
    out: dict[str | None, float] = {}
    for eid in named:
        e = ents.get(eid) if eid else None
        if e and e.get("parent_entity_id") and not e.get("has_children"):
            n = sum(1 for x in ents.values() if x.get("parent_entity_id") == e["parent_entity_id"])
            out[eid] = 1.0 / max(n, 1) + 0.1
        else:
            out[eid] = 1.0
    return out


def seed_insurer(c: httpx.Client, slug: str) -> str:
    maker, checker = pair(c, slug)
    have = {(p["datapoint_key"], p.get("reporting_entity_id"))
            for p in c.get("/v1/provided?framework=insurer_solvency", headers=maker).json()["provided"]
            if p["status"] == "attested" and str(p["reporting_period_end"])[:10] == PERIOD_END}
    stated = 0
    for scope, share in sorted(_scopes(c, maker).items(), key=lambda kv: kv[0] or ""):
        for key, value in demo_figures(slug, scope, share).items():
            if (key, scope) in have:
                continue
            r = c.post("/v1/provided", headers=maker, json={
                "framework": "insurer_solvency", "datapoint_key": key, "value_num": value, "source": "client",
                "provider_name": PROVIDER["treaty" if key.startswith("ri_") else "capital"],
                "data_vintage": PERIOD_END, "reporting_period_end": PERIOD_END, "reporting_entity_id": scope})
            if r.status_code != 201:
                raise SystemExit(f"{slug} {key} ({scope or 'organisation'}): {r.status_code} {r.text[:300]}")
            d = c.post(f"/v1/approvals/{r.json()['approval_request_id']}/decide", headers=checker,
                       json={"decision": "approved", "reason": "demo Solvency II figure checked"})
            if d.status_code != 200:
                raise SystemExit(f"{slug} attest {key}: {d.status_code} {d.text[:300]}")
            stated += 1
    return report(c, slug, maker, f"{stated} values attested")


# ── bank entities ────────────────────────────────────────────────────────────────────────────────────────────────────

NARRATIVE = {   # as scripts/seed_demo_t1_showcase.py, for the institution
    "t1.data_sources": "[Demo text] {name}: counterparties' scope 1, 2 and 3 emissions are taken from their own "
                       "sustainability reports where they publish them; where a counterparty reports no scope 3, the "
                       "institution uses a sector-average intensity per EUR million of revenue for its NACE division "
                       "(demo source, 2024 vintage).",
    "t1.methodology": "[Demo text] {name}: each counterparty's emissions are attributed to the exposure by the exposure's "
                      "gross carrying amount compared to the counterparty's total liabilities and equity, as Annex XL "
                      "column i describes. A missing scope 3 is estimated as the division's intensity multiplied by the "
                      "counterparty's revenue for its financial year ending on or before the reference date.",
    "t1.emission_kinds": "[Demo text] {name} discloses (a) emissions reported by the counterparties and (c) economic "
                         "activity-based emissions (the revenue-based sector averages); it does not use physical "
                         "activity-based emissions.",
}


def _row_text(name: str, table: str, group: str, prompt: str) -> str:
    """As scripts/seed_demo_p3_qualitative.py, for the institution."""
    topic = {"TAB1": "environmental", "TAB2": "social", "TAB3": "governance"}[table]
    return (f"[Demo text] {name} — {prompt.rstrip('.:')}: set out in the institution's {topic} risk framework, approved "
            f"by its management body and reviewed yearly ({group or 'general'}). Illustrative demo answer; not a real "
            "institution's disclosure.")


def seed_bank(c: httpx.Client, slug: str) -> str:
    h = login(c, f"analyst@{slug}.demo", "Demo!analyst1")
    ents = {e["entity_id"]: e["name"] for e in c.get("/v1/filings/entities", headers=h).json().get("entities", [])}
    named = sorted({o["entity_id"] for o in open_obligations(c, h) if o["framework"] == "bank_p3esg" and o.get("entity_id")})
    lines = []
    for eid in named:
        q = c.get("/v1/filings/qualitative/p3esg", headers=h, params={"undertaking": eid, "period_end": PERIOD_END})
        q.raise_for_status()
        name = ents.get(eid, eid)
        values = {}
        for t in q.json()["tables"]:
            for r in t["rows"]:
                if (r.get("value") or "").strip():
                    continue
                if t["table"].startswith("TAB"):
                    values[r["key"]] = _row_text(name, t["table"], r.get("group") or "", r["prompt"])
                elif r["key"] in T1_NARRATIVE:
                    values[r["key"]] = NARRATIVE[r["key"]].format(name=name)
        if values:
            p = c.patch("/v1/filings/qualitative/p3esg", headers=h,
                        json={"values": values, "undertaking": eid, "period_end": PERIOD_END})
            if p.status_code != 200:
                raise SystemExit(f"{slug} {name}: {p.status_code} {p.text[:300]}")
        lines.append(f"{name}: {len(values)} rows authored")
    return report(c, slug, h, "; ".join(lines))


def report(c: httpx.Client, slug: str, h: dict, done: str) -> str:
    """What was done, and every open obligation's remaining preflight gaps."""
    out = [f"{slug}: {done}"]
    for ob in open_obligations(c, h):
        gaps = preflight_gaps(c, h, ob)
        who = ob.get("entity_name") or ob.get("fund_name") or "organisation"
        out.append(f"  {ob['framework']} {ob['period_end']} [{who}]: " + ("no gaps" if not gaps else " | ".join(gaps)))
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8001")
    a = ap.parse_args()
    if not a.base.startswith(("http://localhost", "http://127.0.0.1")):
        print("demo seeding runs against a local development API only", file=sys.stderr)
        return 2
    with httpx.Client(base_url=a.base, timeout=300) as c:
        for slug in INSURERS:
            print(seed_insurer(c, slug))
        for slug in BANKS:
            print(seed_bank(c, slug))
    return 0


if __name__ == "__main__":
    sys.exit(main())
