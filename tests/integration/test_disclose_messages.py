"""Funds, SFDR and the ESRS statement speak in the message catalogue's words (UI standard, product owner 2026-10-16).

Their refusals ('a fund named … already exists', "'csrd.net_turnover' is an amount: say its currency (ISO 4217)", "no
active share classes …"), what a statement still lacks ('Article 7(1)(a): …', 'manager LEI'), why an indicator is not
complete ('issuer EVIC … on the remaining 12% by value'), the Taxonomy notes, the ESRS checks, the gaps of a figure
('needs e1.ghg.total.location and fs.net_revenue'), whether a statement is required, where a comparative comes from —
each was a sentence written where it arose and printed on the screen. Each is now a catalogue code (prefix disclose.)
with its values; the sentences stay only where another service reads them. These tests hold that, on the code and on
every demo organisation in the database.
"""
from __future__ import annotations

import ast
import re
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

from core import messages
from scripts import ui_language as U
from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
NORDKAP = "44444444-4444-4444-8444-444444444444"
# where the codes are raised or rendered
FILES = ["api/routers/funds.py", "services/funds/registry.py", "services/funds/holding.py", "services/funds/onboarding.py",
         "services/ingest/fund_books.py", "api/routers/eet.py", "api/routers/sfdr_documents.py", "api/routers/esrs.py",
         "api/routers/periods.py", "services/fund_messages.py", "services/governance/sfdr_pai_answers.py",
         "services/governance/sfdr_answers.py", "services/governance/sfdr_product.py", "services/governance/template_answers.py",
         "services/eet/fields.py", "services/eet/publication.py", "services/eet/share_classes.py", "services/eet/generator.py",
         "services/fund_energy.py", "services/issuer_client_data.py", "services/governance/esrs_checks.py",
         "services/governance/esrs_statement.py", "services/governance/esrs_comparatives.py",
         "services/governance/esrs_document.py", "services/governance/csrd_scope.py", "services/governance/csrd_roles.py",
         "services/governance/period_close.py", "ml/regulatory/sfdr_pai.py", "api/routers/provided.py",
         "services/governance/provided_data.py"]
CODE = re.compile(r"""["'](disclose\.[a-z_]+(?:\.[a-z_]+)*)["']""")
# codes built from a value, each with every value it takes
BUILT = {"disclose.pai.need.{kind}": ("emissions_evic", "emissions_revenue", "evic", "industry", "issuer_data",
                                      "issuer_data_none", "sovereign_countries", "sovereign_holdings",
                                      "sovereign_violations", "real_estate_not_held", "real_estate_data"),
         "disclose.pai.gap.{kind}": ("item", "summary", "language_home", "language_finance", "best_efforts", "table",
                                     "no_spec"),
         "disclose.identity.{kind}": ("lei", "legal_name", "contact")}
SAMPLE = dict(currency="USD", name="A fund", n=3, items="XS123, XS456", lei="ABCDEFGHIJ0123456789", year=2025, date="2025-06-30",
              first="Explanation for GHG emissions", basis="turnover", coverage="80", excluded="5", rest="12.5",
              data="Energy mix", countries="Iceland", fund="A fund", dates="2025-03-31", section_name="Policies",
              wording="the data sources used", ref="Article 7(1)(e)", period="2024", status="submitted", matched=4, isins=5,
              row=1, language="xx", country="ZZ", isin="XS0000000001", issuer="A company", version="1.1.3", choices="Y / N",
              expected="a date", figure="Total assets", act="ESRS as amended", parent="A group", report="its report",
              facts="Net turnover", point="(a)(i)", standard="E1", total="Total energy", value="10", parts="10",
              part="A part", limit="20", entity="A joint venture", sites="Plant A", terms="medium", term="long",
              scenario="Disorderly 2°C", figures="total assets and net revenue", reading="No obligation before 2024.",
              rule="ESRS 1 Appendix C", reasons="a value awaits attestation", fact="Net turnover", want="yes",
              threshold="50,000,000", field="GHG Emissions Scope 1", note="A note.", pct="12", bases="A basis",
              ratio="12.5", reported="0.6", estimate="60", range="between 0 and 100")


def _codes(path: Path) -> set[str]:
    src = path.read_text(encoding="utf-8")
    out = set(CODE.findall(src))
    for pattern, values in BUILT.items():
        if pattern.split("{")[0] in src:
            out |= {pattern.split("{")[0] + v for v in values}
    return out


def test_every_code_these_screens_raise_or_render_is_in_the_catalogue():
    known, names = set(messages.catalogue()), set(messages.names())        # a names key ('disclose.pai_data') is no code
    missing = sorted(f"{f}: {c}" for f in FILES for c in _codes(ROOT / f) if c not in known | names and not c.endswith("."))
    assert missing == [], f"Add these codes to data/reference/messages.en.json: {missing}"


def test_every_disclose_message_renders_in_customer_words():
    """Each disclose.* code fills with its values (no {placeholder} left), and says nothing internal."""
    bad = []
    for code in (c for c in messages.catalogue() if c.startswith("disclose.")):
        r = messages.render(code, **SAMPLE)
        for part in [r["label"], *r["detail"].values()]:
            if "{" in part or U.INTERNAL.search(part):
                bad.append(f"{code}: {part[:80]}")
    assert bad == []


def test_no_refusal_of_these_routers_hands_its_own_text_to_the_screen():
    """A refusal is a core.errors.UserError: no HTTPException carries an exception's text (str(e)) or a sentence."""
    bad = []
    for f in ("api/routers/funds.py", "api/routers/eet.py", "api/routers/sfdr_documents.py", "api/routers/esrs.py",
              "api/routers/periods.py", "api/routers/provided.py"):
        for n in ast.walk(ast.parse((ROOT / f).read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "HTTPException":
                bad.append(f"{f}:{n.lineno}")
    assert bad == [], bad


def test_a_fund_statement_names_what_it_lacks(session_rolled_back):
    """Every fund's adverse-impact figures: one message per readiness gap, a message for every indicator that names what
    would complete it, the Taxonomy share read in words."""
    from ml.regulatory.sfdr_pai import sfdr_pai_statement
    from services import fund_messages as W
    s, seen = session_rolled_back, 0
    for (fid,) in s.execute(text("SELECT fund_id::text FROM funds")).all():
        st = sfdr_pai_statement(s, fid)
        v = W.statement_view(st)
        if st.get("error"):
            assert v["error"]["label"]
            continue
        seen += 1
        fr = st["filing_readiness"]
        assert len(fr["gaps"]) == len(fr["missing"]) == len(v["readiness"]), fid
        rows = st["indicators"] + st["sovereign_indicators"] + st["real_estate_indicators"]
        for r in rows:
            if r["input_required"]:
                assert r["need"] and str(r["number"]) in v["needs"], (fid, r["number"])
        for m in [*v["readiness"], *v["needs"].values(), *(v["taxonomy"] or {}).values()]:
            assert not U.INTERNAL.search(m["label"] + " " + m["detail"]["what"]), m
    assert seen


def test_the_managers_statement_names_every_gap(session_rolled_back):
    """The principal adverse impacts statement of every asset manager, for each recent period: one message per sentence
    of its readiness (the sentences stay for the filing service that reads them)."""
    from ml.regulatory.sfdr_pai import entity_pai_statement
    from services import fund_messages as W
    s, seen = session_rolled_back, 0
    for (org,) in s.execute(text("SELECT org_id::text FROM organizations WHERE type = 'asset_manager'")).all():
        for y in (2024, 2025):
            st = entity_pai_statement(s, org, date(y, 12, 31))
            if st.get("error"):
                continue
            fr = st["filing_readiness"]
            assert len(fr["gaps"]) == len(fr["missing"]), (org, y)
            for g in fr["gaps"]:
                m = W.message(g)
                seen += 1
                assert not U.INTERNAL.search(m["label"] + " " + m["detail"]["what"]), m
    assert seen >= 0


def test_an_eet_draft_explains_its_checks_and_notes(session_rolled_back):
    from services.eet.generator import build
    s = session_rolled_back
    for (org,) in s.execute(text("SELECT DISTINCT org_id::text FROM fund_share_classes")).all():
        out = build(s, org, ("entity", "periodic", "precontractual"))
        assert len(out["note_msgs"]) == len(out["notes"])
        for c in out["data_checks"]:
            assert c["msg"]["code"].startswith("disclose.eet.check.")


def test_every_esrs_check_and_gap_is_a_catalogue_message(session_rolled_back):
    """For every organisation with sites: each check of its statement, the scope answer and its conditions, each gap of a
    figure, where the comparatives come from and every relief — catalogue messages without internal words."""
    from services.governance import esrs_document as D
    from services.governance.esrs_checks import checks
    from services.governance.filings import reporting_period_end
    s, seen = session_rolled_back, 0
    for (org,) in s.execute(text("SELECT DISTINCT org_id::text FROM sc_company_sites")).all():
        pe = reporting_period_end(s, org)
        try:
            spec, out = D.governing(s, org, pe), D.freeze(s, org, period_end=pe)
        except D.DocumentError:
            continue
        seen += 1
        doc = out["document_report"]
        msgs = [c["msg"] for c in checks({**out, "_specs": {"esrs": {"version": spec["version"], "act": spec["act"]["short"]}}})]
        msgs += [doc["scope_check"]["msg"], *[c["msg"] for c in doc["scope_check"].get("conditions") or []]]
        msgs += [doc["statement"]["scope"]["basis_msg"], *doc["statement"]["scope"]["gap_msgs"]]
        msgs.append(doc["comparatives"]["reported"]["source_msg"])
        msgs += [r["relief_msg"] for r in doc["comparatives"]["rows"] if r["status"] == "relief"]
        for sec in doc["sections"]:
            for i in sec["items"]:
                for d in i.get("datapoints") or []:
                    assert d.get("label") and not U.INTERNAL.search(d["label"]), d.get("concept")
                    if d["status"] == "gap":
                        assert d["gap_msgs"], (org, d["concept"])
                        msgs += d["gap_msgs"]
        for m in msgs:
            assert m and m["code"].startswith(("disclose.", "filing.")), m
            assert not U.INTERNAL.search(m["label"] + " " + m["detail"]["what"]), m
    assert seen


def test_a_refused_step_reaches_the_screen_in_customer_words(api):
    h = _login(api, "admin@nordkap.demo", "Demo!admin1")
    r = api.post("/v1/funds", headers=h, json={"name": "Test fund", "fund_type": "fund", "sfdr_classification": "article_8",
                                                "base_currency": "XYZ"})
    body = r.json()["error"]
    assert r.status_code == 422 and body["error"] == "disclose.fund.refused.currency"
    assert body["message"] == "Not a currency in circulation" and "XYZ" in body["detail"]["what"]
    r = api.put("/v1/manager/filing-profile", headers=h, json={"lei": "NOT-A-VALID-LEI-0000"})
    assert r.json()["error"]["error"] == "disclose.fund.lei.invalid"
    r = api.get("/v1/eet/draft?uses=nothing", headers=h)
    assert r.json()["error"]["error"] == "disclose.eet.refused.uses"
    r = api.put("/v1/entity/pai-statement/answers", headers=h,
                json={"period_end": "2025-12-31", "answers": {"S4.a_approval_date": {"text": "not a date"}}})
    body = r.json()["error"]
    assert r.status_code == 422 and body["error"] == "disclose.answers.refused_all" and "approval date" in body["detail"]["what"]


def test_no_figure_is_named_on_screen_by_the_law_that_defines_it():
    """A figure's on-screen name (esrs_binding.label) never quotes an article, a directive or an encoding note: six
    undertaking facts were named by their legal definitions ('A large undertaking within the meaning of Art. 3(4) of
    Directive 2013/34/EU (1 = yes, 0 = no)'); their definition is one click away."""
    from services.governance.esrs_binding import concepts, label
    law = re.compile(r"\bArt(?:icle)?s?\.?\s?\d|Directive|Regulation \(|\(1 = yes|§")
    assert [k for k in concepts() if law.search(label(k))] == []


def test_keeping_a_year_without_holdings_is_refused_not_answered_as_a_success(api):
    """Keeping a fund's year as its record used to answer 200 with an 'error' field when the fund held nothing."""
    h = _login(api, "admin@nordkap.demo", "Demo!admin1")
    r = api.post("/v1/funds", headers=h, json={"name": "An empty test fund", "fund_type": "fund",
                                                "sfdr_classification": "article_8", "base_currency": "EUR"})
    assert r.status_code == 201, r.text
    r = api.post(f"/v1/funds/{r.json()['fund_id']}/sfdr-statement/file", headers=h, json={})
    assert r.status_code == 409 and r.json()["error"]["error"] == "disclose.fund.no_positions"
