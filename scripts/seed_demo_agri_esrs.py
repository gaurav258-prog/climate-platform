"""The nine agri demo companies state their ESRS sustainability statement (E1, E3, E4) for the financial year ending
2025-12-31 — DEMO data for fictional companies (figures and narratives made up, not regulatory, not validated, no real
company), through the app's own governed routes, the way tests/integration/test_e2e_esrs_statement.py does:

  role         POST /v1/periods/role (maker states, checker approves): 'individual' for each company at organisation
               level and for Terra Foods SA; Terra Ingredients BV and Kumasi Growers Farm Ltd are 'exempt_subsidiary'
               (included in the parent's consolidated report — they file no statement of their own)
  facts        POST /v1/provided (framework 'esrs', four eyes): size class, PIE, employees, net turnover, first reporting
               year, balance-sheet total and net revenue, and the E1 / E3 figures (energy mix, Scopes 1-3, targets,
               water); for a company in its second year (first year 2024) the FY2024 figures as its comparatives
  election     a company not exceeding EUR 450m or 1 000 employees states that its Member State did not apply the
               Art. 5(2) derogation (PATCH /v1/calc-settings, csrd_member_state_derogation = not_exempted)
  items        PUT /v1/esrs/answers: materiality, then every 'shall' item of a material topic filled ('[Demo text] …'),
               ticked, omitted as not applicable where its printed condition does not apply, or under a phase-in the
               checks verify (E1-9 / E3-5 / E4 in the first three years of a wave-one undertaking; Scope 3 for one not
               exceeding 750 employees)
  close        POST /v1/periods/close (four eyes), once nothing blocks

Idempotent: a value already attested (or awaiting attestation) for the period is left as it is; a role, answer or close
already in place is not stated again. Creates no filing. Local demo only: logs in once per user with the seeded demo
credentials (scripts/seed_demo_population.py, scripts/seed_auth_demo.py).

  venv/bin/python scripts/seed_demo_agri_esrs.py [--base http://localhost:8001] [--no-close]
"""
from __future__ import annotations

import argparse
import sys
import time

import httpx

PE, PREV = "2025-12-31", "2024-12-31"
DEMO = "[Demo text]"
# slug: name, employees, net turnover EUR, total assets EUR, first reporting year, E3 material, E4 material
COMPANIES = {
    "andalus": ("Andalus Olive Group (demo)", 1450, 620e6, 540e6, 2024, True, True),
    "bavariafoods": ("Bavaria Foods AG (demo)", 3200, 1350e6, 1100e6, 2024, False, False),
    "douro": ("Douro Alimentar (demo)", 640, 210e6, 190e6, 2025, True, False),
    "flevo": ("Flevo Agro (demo)", 820, 390e6, 310e6, 2025, False, False),
    "oranje": ("Oranje Foods NV (demo)", 2100, 880e6, 760e6, 2024, False, False),
    "padania": ("Padania Alimentari (demo)", 1050, 470e6, 400e6, 2025, True, False),
    "provence": ("Provence Agroalimentaire (demo)", 710, 260e6, 230e6, 2025, True, False),
    "skane": ("Skåne Foods (demo)", 560, 190e6, 160e6, 2025, False, False),
    "terra": ("Terra Foods (demo)", 1200, 500e6, 420e6, 2024, True, False),
}
TERRA_FOODS = "e304ce79-c45c-45a5-9f93-8f6bb9f76dc7"
TERRA_EXEMPT = {"dcc8e50b-fc80-4fc4-bf74-ada0614c0bdb": "Terra Ingredients BV",
                "16c300d0-ec3e-46d1-a408-4555376381a7": "Kumasi Growers Farm Ltd"}
PARENT = {"parent_name": "Terra Group", "parent_registered_office": "Lisbon, Portugal (demo)",
          "parent_report_ref": "Terra Group consolidated management report FY2025, sustainability statement (demo)"}
MONEY = {"csrd.net_turnover", "fs.total_assets", "fs.net_revenue", "fs.net_revenue_high_impact",
         "e1.transition_plan.investments", "e1.actions.capex", "e1.actions.opex"}
STATIC = ("e1.targets.", "e1.ghg.scope1.eu_ets_pct", "esrs2.gov3.")         # the same figure in both years
S3_ITEMS = {"E1-6.44c", "E1-6.44d", "E1-6.51", "E1-6.52", "E1-6.52a", "E1-6.52b", "E1-6.53"}
APPLIES = ("GHG emission reduction targets", "high climate impact sectors", "where applicable", "where material")
TICKED = {"E1-1.16i": True}                                            # the transition plan is approved by the board
NARRATIVE = {
    "ESRS2-GOV-3": "a share of the executive board's variable pay is linked to the Scope 1 and 2 reduction target.",
    "E1-1": "the transition plan, approved by the board in 2024, targets a 42% cut in Scope 1 and 2 emissions by 2030 "
            "against 2023 through heat-pump and biomass process heat, renewable power contracts and fleet electrification.",
    "ESRS2-SBM-3": "the resilience analysis covers all owned processing plants and the main sourcing regions under a "
                   "high-emission and a 1.5°C scenario over short, medium and long horizons; drought and heat at sourcing "
                   "regions are the main exposures, mitigated by supplier diversification and irrigation support.",
    "ESRS2-IRO-1": "climate hazards were screened per site with the platform's hazard scores and transition events with "
                   "carbon-price and regulation scenarios; exposure was assessed against site carrying amounts and revenue.",
    "E1-2": "the group climate policy covers mitigation, adaptation, energy efficiency and renewable energy deployment "
            "across own operations and key suppliers.",
    "E1-3": "key actions in the year: boiler replacement at two plants, rooftop solar, and a renewable power purchase "
            "agreement; their CapEx and OpEx are in the notes on property, plant and equipment and operating costs.",
    "E1-4": "the targets are absolute Scope 1 and 2 targets set against a 2023 base year, aligned with a 1.5°C pathway; "
            "stakeholders were consulted through the supplier and employee panels.",
    "E1-5": "high climate impact sectors: NACE C10 food manufacturing and A01 crop production; energy and revenue "
            "reconcile to the cost of energy and revenue lines of the financial statements.",
    "E1-6": "emissions reconcile to the operational boundary of the financial statements; no significant change in the "
            "reporting boundary in the year.",
    "E1-9": "omitted under the phase-in.",
    "E3": "water is managed through the water policy (sourcing, treatment and pollution prevention); actions and targets "
          "focus on sites in areas of water stress, with a 15% reduction target for consumption by 2030 against 2023.",
}


def _login(c: httpx.Client, email: str, pw: str) -> dict:
    for _ in range(8):
        r = c.post("/v1/auth/login", json={"email": email, "password": pw})
        if r.status_code == 429:
            time.sleep(30)
            continue
        r.raise_for_status()
        return {"Authorization": "Bearer " + r.json()["access_token"]}
    raise SystemExit(f"login {email}: still rate-limited")


def _ok(r: httpx.Response, what: str, codes=(200,)) -> dict:
    if r.status_code not in codes:
        raise SystemExit(f"{what}: {r.status_code} {r.text[:400]}")
    return r.json()


def _approve(c, checker, rid, why="demo value checked"):
    for _ in range(10):        # the request's own transaction may still be committing when its response arrives
        r = c.post(f"/v1/approvals/{rid}/decide", headers=checker, json={"decision": "approved", "reason": why})
        if r.status_code != 404:
            break
        time.sleep(0.5)
    _ok(r, f"approve {rid}")


def figures(turnover: float, assets: float, employees: int, e3: bool, scope3: bool) -> dict:
    """Plausible demo figures from the company's size; every stated total is exactly the sum of its parts."""
    m = turnover / 1e6
    gas, oil, fpur = round(m * 190), round(m * 16), round(m * 70)
    fossil = gas + oil + fpur
    rfuel, rpur, rself = round(m * 25), round(m * 85), round(m * 20)
    renewable, nuclear = rfuel + rpur + rself, round(m * 14)
    s1 = round(gas * 0.202 + oil * 0.267)
    s2l, s2m = round((fpur + rpur + nuclear) * 0.24), round(fpur * 0.38)
    base = round((s1 + s2m) * 1.08)
    f = {"fs.total_assets": assets, "fs.net_revenue": turnover, "fs.net_revenue_high_impact": turnover,
         "fs.energy_high_impact": fossil + nuclear + renewable,
         "esrs2.gov3.remuneration_climate_pct": 5, "e1.transition_plan.investments": round(turnover * 0.012),
         "e1.actions.ghg_reduction.achieved": round(s1 * 0.04), "e1.actions.ghg_reduction.expected": round(s1 * 0.25),
         "e1.actions.capex": round(turnover * 0.01), "e1.actions.opex": round(turnover * 0.002),
         "e1.targets.ghg.absolute": round(base * 0.42), "e1.targets.ghg.intensity": 0.12,
         "e1.targets.ghg.share_per_scope": 100, "e1.targets.base_year": 2023, "e1.targets.baseline": base,
         "e1.targets.value_2030": round(base * 0.58), "e1.targets.value_2050": round(base * 0.1),
         "e1.targets.lever_contribution": round(base * 0.42),
         "e1.energy.total": fossil + nuclear + renewable, "e1.energy.fossil": fossil, "e1.energy.nuclear": nuclear,
         "e1.energy.renewable": renewable, "e1.energy.renewable.fuel": rfuel, "e1.energy.renewable.purchased": rpur,
         "e1.energy.renewable.self_generated": rself, "e1.energy.fossil.coal": 0, "e1.energy.fossil.oil": oil,
         "e1.energy.fossil.natural_gas": gas, "e1.energy.fossil.other": 0, "e1.energy.fossil.purchased": fpur,
         "e1.energy.production.renewable": rself, "e1.energy.production.non_renewable": 0,
         "e1.ghg.scope1.gross": s1, "e1.ghg.scope1.eu_ets_pct": 35, "e1.ghg.scope2.location": s2l,
         "e1.ghg.scope2.market": s2m, "e1.ghg.scope1.consolidated_group": s1, "e1.ghg.scope2.consolidated_group": s2l,
         "e1.ghg.scope1.outside_group": 0, "e1.ghg.scope2.outside_group": 0,
         "e1.removals.total": 0, "e1.credits.cancelled": 0, "e1.credits.planned_cancellation": 0}
    if scope3:
        cats = {"1": round(m * 700), "4": round(m * 80), "9": round(m * 55), "12": round(m * 25)}
        s3 = sum(cats.values())
        f.update({f"e1.ghg.scope3.by_category@{k}": v for k, v in cats.items()})
        f.update({"e1.ghg.scope3.total": s3, "e1.ghg.total.location": s1 + s2l + s3, "e1.ghg.total.market": s1 + s2m + s3})
    if e3:
        w = round(m * 1800)
        f.update({"e3.water.consumption": w, "e3.water.consumption_at_risk": round(w * 0.6),
                  "e3.water.recycled_reused": round(w * 0.12), "e3.water.stored": round(w * 0.05),
                  "e3.water.storage_change": round(w * 0.004)})
    return f


class Undertaking:
    def __init__(self, c, maker, checker, slug, entity_id, label):
        self.c, self.maker, self.checker, self.slug, self.eid, self.label = c, maker, checker, slug, entity_id, label
        self.q = f"?entity_id={entity_id}" if entity_id else ""

    def statement(self) -> dict:
        return _ok(self.c.get(f"/v1/esrs/statement{self.q}", headers=self.maker), f"{self.label} statement")

    def role(self, role: str, **extra):
        live = _ok(self.c.get(f"/v1/periods/role?period_end={PE}" + (f"&entity_id={self.eid}" if self.eid else ""),
                              headers=self.maker), "role")["role"]
        if live and live["role"] == role:
            return
        r = _ok(self.c.post("/v1/periods/role", headers=self.maker, json={"period_end": PE, "entity_id": self.eid,
                                                                          "role": role, **extra}), "role", (202,))
        _approve(self.c, self.checker, r["approval_request_id"], "demo CSRD role checked")

    def state(self, facts: dict, period_end: str) -> int:
        mine = [p for p in _ok(self.c.get("/v1/provided?framework=esrs", headers=self.maker), "provided")["provided"]
                if p["status"] in ("attested", "pending") and p["reporting_period_end"] == period_end
                and p["reporting_entity_id"] == self.eid]
        have = {(p["datapoint_key"], p.get("breakdown_member")) for p in mine}
        waiting = {p["provided_id"] for p in mine if p["status"] == "pending"
                   and (p["datapoint_key"] + (f"@{p['breakdown_member']}" if p.get("breakdown_member") else "")) in facts}
        if waiting:                                   # a previous run stated it; its second person had not approved yet
            for a in _ok(self.c.get("/v1/approvals?status=pending", headers=self.checker), "approvals"):
                if (a.get("payload") or {}).get("provided_id") in waiting:
                    _approve(self.c, self.checker, a["id"])
        n = 0
        for key, v in facts.items():
            k, _, member = key.partition("@")
            if (k, member or None) in have:
                continue
            body = {"framework": "esrs", "datapoint_key": k, "value_num": v, "reporting_period_end": period_end,
                    "reporting_entity_id": self.eid, "source": "client",
                    "provider_name": "Demo seed (fictional company, illustrative figures)"}
            if k in MONEY:
                body["currency"] = "EUR"
            if member:
                body["breakdown_member"] = member
            r = _ok(self.c.post("/v1/provided", headers=self.maker, json=body), f"{self.label} {key} {period_end}", (201,))
            _approve(self.c, self.checker, r["approval_request_id"])
            n += 1
        return n

    def answer(self, standard: str, answers: dict):
        if not answers:
            return
        out = _ok(self.c.put("/v1/esrs/answers", headers=self.maker,
                             json={"standard": standard, "answers": answers, "entity_id": self.eid}), f"{self.label} {standard}")
        if out.get("refused"):
            raise SystemExit(f"{self.label} {standard} refused: {out['refused'][:3]}")


def _text(name: str, dr: str | None, standard: str) -> str:
    key = next((k for k in NARRATIVE if dr and dr.startswith(k) and standard == "E1"), None)
    body = NARRATIVE.get(key) if key else (NARRATIVE["E3"] if standard == "E3" else None)
    return f"{DEMO} {name}: " + (body or "assessed and described in the undertaking's sustainability statement.")


def items(u: Undertaking, name: str, employees: int, e4: bool):
    """Every 'shall' item of a material topic still missing: answered, ticked, not applicable or phased in."""
    d = u.statement()
    for sec in d["document_report"]["sections"]:
        std = sec["standard"]
        if not (sec.get("topic") or {}).get("material"):
            continue
        answers, dr = {}, None
        for i in sec["items"]:
            if i["kind"] == "heading":
                dr = i["id"]
                continue
            if i["status"] != "missing" or i.get("obligation") != "shall":
                continue
            iid, cond = i["id"], i.get("conditional")
            if dr in ("E1-9", "E3-5") or (std == "E4" and e4):
                pid = {"E1-9": "e1_9_first_years_wave1", "E3-5": "e3_5_first_years_wave1"}.get(dr, "e4_all_wave1")
                answers[iid] = {"omitted": {"reason": "phase_in", "phase_in": pid}}
            elif iid in S3_ITEMS and employees <= 750:
                answers[iid] = {"omitted": {"reason": "phase_in", "phase_in": "e1_6_scope3_total_wave1"}}
            elif cond and not any(a in cond for a in APPLIES):
                answers[iid] = {"omitted": {"reason": "condition_not_applicable",
                                            "statement": f"{DEMO} the condition does not apply to {name}."}}
            elif i["kind"] == "choice":
                answers[iid] = {"ticked": TICKED.get(iid, False)}
            elif i["kind"] == "question" or (i["kind"] == "field" and i.get("narrative")):
                answers[iid] = {"text": _text(name, dr, std)}
            else:
                print(f"  ! {u.label} {iid}: a figure is not stated", file=sys.stderr)
        u.answer(std, answers)


def comparatives(u: Undertaking, name: str):
    """The FY2024 comparatives come from the attested FY2024 figures — the ratios derived from them as the FY2025 ones
    are (E137). A statement of impracticability an earlier run of this script made for a ratio, before the platform
    derived it, is withdrawn (set to null); a comparative still missing is reported, never stated impracticable."""
    rows = (u.statement()["document_report"].get("comparatives") or {}).get("rows") or []
    stale = {f"cmp.{r['concept']}": None for r in rows
             if r["status"] != "missing" and ((r.get("answer") or {}).get("impracticable") or "").startswith(DEMO)}
    if stale:
        u.answer("comparatives", stale)
    for r in rows:
        if r["status"] == "missing":
            print(f"  ! {name}: no FY2024 comparative for {r['concept']}", file=sys.stderr)


def seed(c, slug: str, maker, checker, admin, entity_id=None, label=None) -> str:
    name, emp, turnover, assets, first, e3, e4 = COMPANIES[slug]
    name = label or name
    u = Undertaking(c, maker, checker, slug, entity_id, name)
    u.role("individual", basis=f"{DEMO} large public-interest entity exceeding 500 employees (Art. 5(2)(a)(i))")
    core = {"csrd.large_undertaking": 1, "csrd.public_interest_entity": 1, "csrd.employees_average": emp,
            "csrd.net_turnover": turnover, "csrd.first_reporting_year": first, "csrd.transparency_issuer": 1,
            "esrs.method.physical_risk_level": 30}
    scope3 = emp > 750
    n = u.state({**core, **figures(turnover, assets, emp, e3, scope3)}, PE)
    if first == 2024:                                 # second year: the FY2024 figures are the comparatives (ESRS 1 §83)
        prev = {k: v for k, v in figures(turnover / 1.05, assets / 1.04, emp, e3, scope3).items()}
        n += u.state({k: (figures(turnover, assets, emp, e3, scope3)[k] if k.startswith(STATIC) else v)
                      for k, v in prev.items()}, PREV)
    if (emp <= 1000 or turnover <= 450e6) and admin:
        r = _ok(c.patch("/v1/calc-settings", headers=admin,
                        json={"interpretation": {"csrd_member_state_derogation": "not_exempted"}}), "derogation")
        if r.get("status") == "pending_approval":
            _approve(c, maker, r["request_id"], "demo Member State election checked")
    u.answer("materiality", {
        "E1": {"material": True},
        "E3": {"material": True} if e3 else {"material": False, "explanation": f"{DEMO} operations draw little water "
                                                                               "and no site is in an area of water stress"},
        "E4": {"material": True} if e4 else {"material": False, "explanation": f"{DEMO} no own site in or near a "
                                                                               "biodiversity-sensitive area"}})
    items(u, name, emp, e4)
    comparatives(u, name)
    return f"{name}: {n} value(s) attested"


def close(c, u: Undertaking) -> str:
    q = f"&entity_id={u.eid}" if u.eid else ""
    b = _ok(c.get(f"/v1/periods/close/blockers?period_end={PE}{q}", headers=u.maker), "blockers")["blockers"]
    if b == ["the period is already closed"]:
        return "already closed"
    if b:
        return "not closed: " + "; ".join(b)
    r = _ok(c.post("/v1/periods/close", headers=u.maker, json={"period_end": PE, "entity_id": u.eid}), "close", (202,))
    _approve(c, u.checker, r["approval_request_id"], "demo FY2025 close checked")
    return "closed"


def verify(c, u: Undertaking) -> str:
    d = u.statement()
    bad = {x["rule"]: x["message"][:160] for x in d["checks"] if not x["passed"] and x["severity"] == "blocking"}
    warn = sorted(x["rule"] for x in d["checks"] if not x["passed"] and x["severity"] == "warning")
    pf = c.get(f"/v1/filings/preflight?framework=esrs_pack{u.q.replace('?', '&')}", headers=u.maker)
    p = pf.json() if pf.status_code == 200 else {"error": pf.text[:200]}
    gaps = p.get("gaps") or p.get("blockers") or p.get("error")
    return (f"{u.label}: blocking={bad or 'none'} warnings={warn or 'none'} preflight token="
            f"{'yes' if p.get('confirm_token') else 'no'} gaps={gaps or 'none'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8001")
    ap.add_argument("--no-close", action="store_true")
    ap.add_argument("--only", nargs="*", default=list(COMPANIES))
    a = ap.parse_args()
    if not a.base.startswith(("http://localhost", "http://127.0.0.1")):
        print("demo seeding runs against a local development API only", file=sys.stderr)
        return 2
    with httpx.Client(base_url=a.base, timeout=300) as c:
        for slug in a.only:
            maker = _login(c, f"analyst@{slug}.demo", "Demo!analyst1")
            if slug == "terra":
                checker = _login(c, "approver@terra.demo", "Demo!approve1")
                print(seed(c, slug, maker, checker, None, TERRA_FOODS, "Terra Foods SA"))
                units = [Undertaking(c, maker, checker, slug, TERRA_FOODS, "Terra Foods SA")]
                for eid, nm in TERRA_EXEMPT.items():
                    x = Undertaking(c, maker, checker, slug, eid, nm)
                    x.role("exempt_subsidiary", **PARENT, basis=f"{DEMO} {nm} is included in Terra Group's consolidated "
                           "sustainability statement (Directive 2013/34/EU Art. 19a(9))")
                    units.append(x)
            else:
                checker = _login(c, f"admin@{slug}.demo", "Demo!admin1")
                print(seed(c, slug, maker, checker, checker))
                units = [Undertaking(c, maker, checker, slug, None, COMPANIES[slug][0])]
            if not a.no_close:
                print(f"  close {units[0].label}: {close(c, units[0])}")
            for u in units:
                print("  " + verify(c, u))
    return 0


if __name__ == "__main__":
    sys.exit(main())
