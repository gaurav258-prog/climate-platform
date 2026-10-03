"""The demo asset managers' SFDR PAI statements for 2025 — DEMO data, made up for fictional demo companies (not
regulatory, not validated, no real company's figures), through the app's own paths wherever one exists:

  funds          Amstel, Fjord, Øresund, Seine, Tiber (demo) each get two demo funds (POST /v1/funds)
  holdings       POST /v1/funds/{id}/holdings on each quarter end of 2025 (the statement averages the four: Delegated
                 Regulation (EU) 2022/1288 Art. 6(3)), holding only the four fictional demo issuers that already carry
                 emissions, revenue and EVIC in the reference (DE00ENERGY01, ES00FOODS001, NL00LOGIS001, SE00SOFT0001),
                 with demo PAI 5-14 facts and demo EU Taxonomy KPIs (with the fossil gas / nuclear parts) for them on
                 the upload (org-scoped client data)
  identity       the filing contact email (PATCH /v1/admin/organization); the demo LEIs are left as they are
  PAI answers    PUT /v1/entity/pai-statement/answers for 2025-12-31 — every section item and every Table 1 row's
                 explanation and actions not yet answered (Nordkap too)
  periodic docs  every manager's funds (Nordkap's too): PUT /v1/funds/{id}/sfdr-documents/periodic/answers for every
                 item still missing

Every free text starts with "[Demo text]". Idempotent: a fund is found by name, a position is upserted by the app, an
answer already given is left as it is.

  venv/bin/python scripts/seed_demo_asset_managers.py [--base http://localhost:8001]

Local demo only: logs in with the seeded demo credentials (scripts/seed_demo_population.py, scripts/seed_auth_demo.py).
"""
from __future__ import annotations

import argparse
import random
import sys
import time

import httpx

PERIOD_END = "2025-12-31"
DATES = ("2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31")
D = "[Demo text] "
# slug: (organisation, home language)
MANAGERS = {"amstel": ("Amstel Investment Management (demo)", "nl"), "fjord": ("Fjord Capital (demo)", "no"),
            "oresund": ("Øresund Funds (demo)", "da"), "seine": ("Seine Capital (demo)", "fr"),
            "tiber": ("Tiber Asset Management (demo)", "it")}
NORDKAP = ("nordkap", "Nordkap Asset Management (demo)", "sv")
# the fictional demo issuers' demo PAI 5-14 facts (reported, near the sector / country averages the app checks against)
ISSUERS = {
    "DE00ENERGY01": {"energy_intensity_gwh_per_meur": 0.55, "non_renewable_consumption_pct": 74.0,
                     "non_renewable_production_pct": 58.0, "biodiversity_sensitive_ops": True,
                     "emissions_to_water_tonnes": 42.0, "hazardous_waste_tonnes": 1800.0, "gender_pay_gap_pct": 14.0,
                     "board_female_pct": 33.0},
    "ES00FOODS001": {"energy_intensity_gwh_per_meur": 0.21, "non_renewable_consumption_pct": 72.0,
                     "biodiversity_sensitive_ops": False, "emissions_to_water_tonnes": 12.5,
                     "hazardous_waste_tonnes": 35.0, "gender_pay_gap_pct": 9.5, "board_female_pct": 40.0},
    "NL00LOGIS001": {"energy_intensity_gwh_per_meur": 0.09, "non_renewable_consumption_pct": 80.0,
                     "biodiversity_sensitive_ops": False, "emissions_to_water_tonnes": 0.8,
                     "hazardous_waste_tonnes": 60.0, "gender_pay_gap_pct": 11.0, "board_female_pct": 30.0},
    "SE00SOFT0001": {"energy_consumption_gwh": 12.0, "non_renewable_consumption_pct": 45.0,
                     "biodiversity_sensitive_ops": False, "emissions_to_water_tonnes": 0.0,
                     "hazardous_waste_tonnes": 1.2, "gender_pay_gap_pct": 7.0, "board_female_pct": 44.0},
}
FLAGS = {"ungc_oecd_violation": False, "ungc_oecd_no_monitoring": False, "controversial_weapons": False}
# the fictional demo issuers' demo EU Taxonomy KPIs (%): eligible, aligned and the fossil gas / nuclear parts of the
# aligned share (Delegated Regulation (EU) 2022/1214 Annex XII), turnover- and CapEx-based
TAXONOMY = {"DE00ENERGY01": (60.0, 35.0, 5.0, 0.0, 50.0, 8.0, 0.0), "ES00FOODS001": (10.0, 2.0, 0.0, 0.0, 4.0, 0.0, 0.0),
            "NL00LOGIS001": (25.0, 8.0, 0.0, 0.0, 12.0, 0.0, 0.0), "SE00SOFT0001": (5.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)}
_TAX_FIELDS = ("taxonomy_eligible_pct", "taxonomy_aligned_pct", "taxonomy_fossil_gas_aligned_pct",
               "taxonomy_nuclear_aligned_pct", "taxonomy_aligned_capex_pct", "taxonomy_fossil_gas_aligned_capex_pct",
               "taxonomy_nuclear_aligned_capex_pct")
# two funds per manager: name suffix, SFDR article, {ISIN: base market value EUR}
FUNDS = (("European Sustainable Equity Fund", "article_8",
          {"ES00FOODS001": 30e6, "SE00SOFT0001": 25e6, "NL00LOGIS001": 15e6}),
         ("Energy Transition Fund", "article_8", {"DE00ENERGY01": 20e6, "NL00LOGIS001": 10e6}))


def _login(c: httpx.Client, email: str, pw: str) -> dict:
    for _ in range(6):
        r = c.post("/v1/auth/login", json={"email": email, "password": pw})
        if r.status_code != 429:
            r.raise_for_status()
            return {"Authorization": "Bearer " + r.json()["access_token"]}
        time.sleep(30)
    raise SystemExit(f"login {email}: still rate-limited")


def _ok(r: httpx.Response, what: str) -> dict:
    if r.status_code not in (200, 201):
        raise SystemExit(f"{what}: {r.status_code} {r.text[:400]}")
    return r.json()


def _fund(c: httpx.Client, h: dict, name: str, article: str) -> str:
    """The demo fund, found by name or created through the app (POST /v1/funds, E144)."""
    for f in _ok(c.get("/v1/funds", headers=h), "funds")["funds"]:
        if f["name"] == name:
            return f["fund_id"]
    return _ok(c.post("/v1/funds", headers=h, json={"name": name, "fund_type": "fund", "sfdr_classification": article,
                                                    "base_currency": "EUR"}), f"create {name}")["fund_id"]


def seed_funds(c: httpx.Client, h: dict, slug: str, org: str) -> list[str]:
    rng, out = random.Random(slug), []
    short = org.removesuffix(" (demo)").split()[0]
    for suffix, article, book in FUNDS:
        name = f"{short} {suffix} (demo)"
        fid = _fund(c, h, name, article)
        scale = rng.uniform(0.6, 1.8)
        n_pos = 0
        for q, d in enumerate(DATES):
            holdings = [{"isin": isin, "market_value_eur": round(mv * scale * (1 + 0.025 * q + rng.uniform(-0.02, 0.02)), 2),
                         "asset_class": "equity", "reporting_year": 2024, **ISSUERS[isin], **FLAGS,
                         **dict(zip(_TAX_FIELDS, TAXONOMY[isin]))}
                        for isin, mv in book.items()]
            r = _ok(c.post(f"/v1/funds/{fid}/holdings", headers=h, json={"as_of_date": d, "holdings": holdings}),
                    f"{slug} {name} holdings {d}")
            cov = r["coverage"]
            if cov["unmatched"] or cov["errored"] or r["fx"]["errors"] or r["voluntary_rejected"]:
                raise SystemExit(f"{slug} {name} {d}: {cov['unmatched']} {cov['errored']} {r['fx']['errors']}")
            n_pos += r["positions_created"]
        out.append(f"{name} ({len(book)} holdings x 4 quarter ends = {n_pos} positions)")
    return out


def _has(a) -> bool:
    return bool(a) and (bool((a.get("text") or "").strip()) or a.get("applicable") is False or "ticked" in a
                        or bool(a.get("rows")))


def pai_answers(c: httpx.Client, h: dict, slug: str, org: str, lang: str) -> int:
    """Every item of the 2025 PAI statement not yet answered, answered with demo text."""
    a = _ok(c.get(f"/v1/entity/pai-statement/answers?period_end={PERIOD_END}", headers=h), f"{slug} PAI answers")
    who = org.removesuffix(" (demo)")
    want = {
        "S1.d_summary": {"rows": [
            {"d_language": lang, "d_meets": ["home_official"],
             "d_text": D + f"Summary of the principal adverse impacts of {who} for 2025, in the home language."},
            {"d_language": "en", "d_meets": ["international_finance"],
             "d_text": D + f"{who} considers the principal adverse impacts of its investment decisions; in 2025 its "
                           "largest impacts were greenhouse gas emissions of energy and logistics investees."}]},
        "S4.policies": {"text": D + "Our policy identifies principal adverse impacts by sector exposure and data "
                                    "coverage and prioritises the largest emitters; it is reviewed every year."},
        "S4.a_approval_date": {"text": "2025-03-14"},
        "S4.b_responsibility": {"text": D + "The Chief Investment Officer implements the policy; the risk committee "
                                            "oversees it and reports to the board."},
        "S4.c_methodologies": {"text": D + "Indicators are selected by the severity of the impact (sector intensity) "
                                           "and its probability (data coverage across the holdings)."},
        "S4.d_margin_of_error": {"text": D + "Reported figures carry no stated margin; any estimated figure carries "
                                             "the error of the sector average it rests on."},
        "S4.e_data_sources": {"text": D + "Investee annual reports, the investees' sustainability statements and the "
                                          "platform's reference data."},
        "S4.best_efforts": {"text": D + "Missing data was requested from every investee and from one data provider; "
                                        "figures still missing are disclosed as gaps, not estimated."},
        "S5.a_srd": {"text": D + "Our engagement policy under Article 3g of Directive 2007/36/EC covers voting and "
                                 "dialogue with every listed investee."},
        "S5.b_other": {"text": D + "We engage the largest emitters each year on reduction targets."},
        "S5.2a_indicators": {"text": D + "Indicators 1 to 4 (greenhouse gas emissions and fossil fuel exposure)."},
        "S5.2b_adaptation": {"text": D + "Escalation to a vote against management after two periods without a "
                                         "reduction in principal adverse impacts."},
        "S6.adherence": {"text": D + "We adhere to the OECD Guidelines for Multinational Enterprises and the UN "
                                     "Global Compact principles."},
        "S6.2a_indicators": {"text": D + "Indicators 10 and 11."},
        "S6.2b_methodology": {"text": D + "Quarterly controversy screening of every holding against the UN Global "
                                          "Compact and OECD Guidelines."},
        "S6.2c_scenario": {"ticked": False},
        "S6.2d_no_scenario": {"text": D + "No forward-looking climate scenario is used: our holding period is shorter "
                                          "than the horizon of the scenarios available."},
    }
    for r in a["rows"]:
        want[f"{r['key']}.expl"] = {"text": D + f"{r['label']}: the 2025 figure is the average of the four quarter "
                                                "ends; it reflects the funds' holdings in energy and logistics."}
        want[f"{r['key']}.action"] = {"text": D + "Engagement with the investees concerned continues; target for the "
                                                  "next reference period: a lower figure at equal coverage."}
    given = a.get("answers") or {}
    given.update({f"{r['key']}.{col}": {"text": r[col]} for r in a["rows"] for col in ("expl", "action") if r.get(col)})
    todo = {k: v for k, v in want.items() if not _has(given.get(k))}
    if todo:
        _ok(c.put("/v1/entity/pai-statement/answers", headers=h, json={"period_end": PERIOD_END, "answers": todo}),
            f"{slug} PAI answers save")
    return len(todo)


# the answer to each choice of the periodic template (Art. 8: E/S promoted, some sustainable investment) — else unticked
CHOICES = {"q_sust_obj.no.es_with_si": {"ticked": True, "percent": 10.0},
           "q_sust_obj.no.es_with_si.env_taxonomy": {"ticked": True},
           "q_sust_obj.no.es_with_si.env_non_taxonomy": {"ticked": True}}
ALLOCATION = {"investments": 100.0, "n1_aligned": 85.0, "n2_other": 15.0, "n1a_sustainable": 10.0,
              "n1b_other_es": 75.0, "taxonomy_aligned": 5.0, "other_environmental": 4.0, "social": 1.0}


def periodic_answers(c: httpx.Client, h: dict, fid: str) -> tuple[int, list[str]]:
    d = _ok(c.get(f"/v1/funds/{fid}/sfdr-documents/periodic", headers=h), f"periodic {fid}")
    items = d["items"]
    todo = {}
    for i in items:
        if i["status"] != "missing" or i.get("source") != "input":
            continue
        k, iid = i["kind"], i["id"]
        if k in ("question", "field"):
            todo[iid] = {"text": D + f"{d['fund']['name']} — {i['label'][:120]} Answered for the 2025 reference "
                                     "period from the fund's holdings and engagement records."}
        elif k == "choice":
            todo[iid] = CHOICES.get(iid, {"ticked": False})
        elif k == "chart":
            labels = [x["id"] for x in items if x.get("parent") == iid and x["kind"] == "chart_label"]
            todo[iid] = {"values": {x: ALLOCATION[x.split(".", 1)[1]] for x in labels if x.split(".", 1)[1] in ALLOCATION}}
        elif k == "table":
            cols = [x["id"] for x in items if x.get("parent") == iid and x["kind"] == "table_column"]
            todo[iid] = {"rows": [{col: D + "see the fund's annual report" for col in cols}]}
    if todo:
        r = _ok(c.put(f"/v1/funds/{fid}/sfdr-documents/periodic/answers", headers=h, json={"answers": todo}),
                f"periodic answers {fid}")
        if r.get("refused"):
            raise SystemExit(f"periodic answers {fid} refused: {r['refused']}")
    left = [i["id"] for i in _ok(c.get(f"/v1/funds/{fid}/sfdr-documents/periodic", headers=h), "periodic")["items"]
            if i["status"] == "missing"]
    return len(todo), left


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8001")
    a = ap.parse_args()
    if not a.base.startswith(("http://localhost", "http://127.0.0.1")):
        print("demo seeding runs against a local development API only", file=sys.stderr)
        return 2
    with httpx.Client(base_url=a.base, timeout=300) as c:
        for slug, (org, lang) in MANAGERS.items():
            maker = _login(c, f"analyst@{slug}.demo", "Demo!analyst1")
            admin = _login(c, f"admin@{slug}.demo", "Demo!admin1")
            funds = seed_funds(c, maker, slug, org)
            prof = _ok(c.get("/v1/manager/filing-profile", headers=maker), f"{slug} profile")
            if not prof.get("filing_contact_email"):
                _ok(c.patch("/v1/admin/organization", headers=admin,
                            json={"filing_contact_email": f"compliance@{slug}.demo"}), f"{slug} contact email")
            n = pai_answers(c, maker, slug, org, lang)
            print(f"{slug}: {'; '.join(funds)}; {n} PAI statement answers given")
            for f in _ok(c.get("/v1/funds", headers=maker), f"{slug} funds")["funds"]:
                n, left = periodic_answers(c, maker, f["fund_id"])
                print(f"{slug}: {f['name']}: {n} periodic answers given; still missing: {left or 'none'}")
        slug, org, lang = NORDKAP
        maker = _login(c, f"analyst@{slug}.demo", "Demo!analyst1")
        print(f"{slug}: {pai_answers(c, maker, slug, org, lang)} PAI statement answers given")
        for f in _ok(c.get("/v1/funds", headers=maker), "nordkap funds")["funds"]:
            n, left = periodic_answers(c, maker, f["fund_id"])
            print(f"{slug}: {f['name']}: {n} periodic answers given; still missing: {left or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
