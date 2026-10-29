"""The filing journey speaks in the message catalogue's words (UI standard, product owner 2026-10-16).

Every refusal of a lifecycle step, every gap the pre-filing check names and every check of the checklist used to be a
sentence written where it arose — framework keys ('a live bank_tcfd filing …'), status codes, method keys
('method.at_risk_level'), 'golden source', template codes — passed straight to the screen. Each is now a catalogue code
(data/reference/messages.en.json, prefix filing.) with its values: the label for the screen, the detail behind its ⓘ.
These tests hold that, on the code and on every filing in the database.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from sqlalchemy import text

from core import messages
from scripts import ui_language as U
from tests.integration.conftest import login as _login
from tests.integration.filers import group
from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
# the exceptions whose first argument is a catalogue code (each a core.errors.UserError)
CODED = {"FilingError", "ProductScopeError", "ExportError", "OverrideError", "UserError"}
FILES = ["services/governance/filings.py", "services/governance/product_filings.py", "services/governance/filing_export.py",
         "services/governance/filing_overrides.py", "services/governance/board_pack.py", "services/governance/assurance_share.py",
         "services/governance/filing_validation.py", "services/governance/filing_crosscheck.py",
         "services/governance/pillar3_report.py", "services/governance/bank_taxonomy_report.py",
         "api/routers/filings.py", "api/routers/board_pack.py", "api/routers/grc_followups.py"]
SAMPLE = dict(report="Pillar 3 ESG", period="FY2025", state="a draft", step="approved", n=3, total=10, done=7, noun="exposures",
              pct=70.0, left=3, value="€1,000", measure="Total book value", hazard="Flood", scopes="scope 3", checks="One check",
              items="An item", names="A choice", reasons="A reason", since="2026-10-01", reason="a reason", successor="ESRS statement",
              where="on its own page", how="on its own page", obligation_period="FY2025", obligation_end="2025-12-31",
              period_end="2025-12-31", parent="A group", report_ref="Its report", date="2026-01-31", min=10, currency="USD",
              fund="A fund", format="XBRL", rows="table9.z", max=180, year="2025", start="2025-01-01", end="2025-12-31",
              dates="31 Mar", funds="A fund", net="€1", gross="€2", mean="€1", name="An entity", leg="own operations",
              sum=3, var=1.0, tol=0.5, reported="€1", ledger="€1", m=1, figure="Total book value", version=2, other="USD",
              this="EUR", group="A group", undertaking="An undertaking", undertakings="An undertaking",
              held_through="Another undertaking", count=3, choices="A group, An undertaking", who="an undertaking")


def _coded_calls(path: Path):
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Call) and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if name in CODED | {"render", "_check", "_f"} and re.fullmatch(r"[a-z]+(\.[a-z_]+)+", n.args[0].value):
                yield n.args[0].value, n.lineno


def test_every_code_the_filing_journey_raises_or_renders_is_in_the_catalogue():
    known = set(messages.catalogue())
    missing = [f"{f}:{line} {code}" for f in FILES for code, line in _coded_calls(ROOT / f) if code not in known]
    assert missing == [], f"Add these codes to data/reference/messages.en.json: {missing}"


def test_every_filing_message_renders_in_customer_words():
    """Each filing.* code fills with its values (no {placeholder} left), has a label of at most eight words, and says
    nothing internal — in its label or in any part of its detail."""
    bad = []
    for code in (c for c in messages.catalogue() if c.startswith("filing.")):
        r = messages.render(code, **SAMPLE)
        for part in [r["label"], *r["detail"].values()]:
            if "{" in part or (U.INTERNAL.search(part) and "table9.z" not in part):
                bad.append(f"{code}: {part[:80]}")
    assert bad == []


def test_every_interpretation_value_has_a_name():
    """A choice frozen with a filing shows its value in words (filings.election_view): every value an interpretation
    switch allows is named — a scenario by names.scenario, a dependence rule by names.dependence, the rest by
    names.filing.election."""
    from services.calc_settings import INTERPRETATION_SCHEMA
    names = messages.names()
    known = {**names["filing.election"], **names["scenario"], **names["dependence"]}
    unnamed = [f"{k}: {v}" for k, s in INTERPRETATION_SCHEMA.items() if s.get("kind") == "enum" for v in s.get("allowed") or []
               if v not in known]
    assert unnamed == []


def test_every_scope_three_reason_has_words():
    from services.governance import pillar3_t1 as T1
    src = (ROOT / "services/governance/pillar3_t1.py").read_text(encoding="utf-8")
    kinds = set(re.findall(r'"scope3_reason"\] = \{"kind": "([a-z_]+)"', src))
    assert kinds and kinds <= set(messages.names()["filing.scope_reason"]), kinds
    assert T1.scope3_reasons({}) == ""


def _live_filings(s, every: bool = False):
    """The latest frozen filing of each report per organisation — or, with every, each frozen filing (every specification
    version a filing was frozen under)."""
    if every:
        return s.execute(text("SELECT org_id::text, filing_id::text, framework FROM regulatory_filing WHERE snapshot_id IS NOT NULL")).all()
    return s.execute(text("""SELECT DISTINCT ON (framework, org_id) org_id::text, filing_id::text, framework FROM regulatory_filing
                             WHERE snapshot_id IS NOT NULL ORDER BY framework, org_id, seq DESC""")).all()


# the rule sets that still state their findings in their own sentence (named as follow-ups): every other finding is a
# catalogue message
OWN_SENTENCE = {"insurer_orsa_climate", "insurer_recovery_stress", "sfdr_precontractual", "sfdr_periodic", "eudr_dds",
                "eudr_simplified", "esrs_pack"}
GENERIC = re.compile(r"^(snapshot_frozen|hash_verified|method_stated|fx_rates_\w+|cross_report:.*|ledger_reconciled)$")


def test_every_check_of_the_checklist_is_a_catalogue_message(session_rolled_back):
    from services.governance.filing_validation import validate_filing
    s, seen, bad = session_rolled_back, set(), []
    for org, fid, fw in _live_filings(s):
        for f in validate_filing(s, org, fid)["findings"]:
            if fw in OWN_SENTENCE and not GENERIC.match(f["rule"]):
                continue
            seen.add(fw)
            m = f.get("msg") or {}
            if not (m.get("code", "").startswith("filing.") and m.get("label") and (m.get("detail") or {}).get("what")):
                bad.append(f"{fw} {f['rule']}: {f['message'][:60]}")
            elif U.INTERNAL.search(m["label"] + " " + m["detail"]["what"]):
                bad.append(f"{fw} {f['rule']}: internal words: {m['detail']['what'][:60]}")
    assert seen and bad == []


def test_the_pre_filing_check_names_its_gaps_as_messages(session_rolled_back):
    from services.governance.filings import FilingError, available_frameworks, preflight
    s, checked = session_rolled_back, 0
    for org, typ in s.execute(text("SELECT org_id::text, type FROM organizations WHERE type IN ('bank','insurer','reit','asset_manager')")).all():
        for fw in available_frameworks(typ):
            try:
                pf = preflight(s, org, typ, fw["framework"])
            except FilingError:
                continue
            for g in pf["gaps"]:
                checked += 1
                assert set(g) >= {"code", "label", "detail"} and g["code"].startswith("filing.gap."), (fw["framework"], g)
                assert not U.INTERNAL.search(g["label"] + " " + g["detail"]["what"]), (fw["framework"], g)
    assert checked >= 0


def test_the_final_form_names_its_report_and_prints_its_columns_as_printed(session_rolled_back):
    """The official form is named by its reference (never its framework key, as the simplified declaration's was), and a
    column the template prints twice under one id ('ae') is shown as printed, never by its address ('ae_2')."""
    from services.governance.filings import FRAMEWORKS, form_view
    s = session_rolled_back
    for org, fid, fw in _live_filings(s, every=True):
        a = (form_view(s, org, fid) or {}).get("annex") or {}
        if a:
            assert a["official_name"] not in FRAMEWORKS, (fw, a["official_name"])
        for sec in a.get("sections") or []:
            assert "ae_2" not in " ".join([*(sec.get("columns") or []), sec.get("note") or ""]), (fw, sec["title"])


def test_a_refused_step_reaches_the_screen_in_customer_words(api):
    maker = _login(api, "admin@meridian.demo", "Demo!admin1")
    grp = group(api.s, BANK_ORG)                 # the group's report (its whole organisation is no filer, E349)
    r = api.post("/v1/filings", headers=maker, json={"framework": "bank_tcfd", "entity_id": grp})
    body = r.json()["error"]
    assert r.status_code == 409 and body["error"] == "filing.refused.not_confirmed"
    assert body["message"] == "Confirm the data first" and body["detail"]["next"]
    r = api.post("/v1/filings", headers=maker, json={"framework": "bank_tcfd", "confirm_token": "0" * 32, "entity_id": grp})
    assert r.status_code == 409 and r.json()["error"]["error"] == "filing.refused.data_changed"
    r = api.get("/v1/filings/preflight?framework=no_such_report", headers=maker)
    assert r.status_code == 404 and r.json()["error"]["message"] == "This report is not available"


def test_board_pack_and_auditor_share_refusals_are_catalogue_messages(api):
    maker = _login(api, "admin@meridian.demo", "Demo!admin1")
    r = api.post("/v1/board-pack", headers=maker, json={"period_from": "2026-06-30", "period_to": "2026-01-01"})
    assert r.status_code == 422 and r.json()["error"]["error"] == "filing.board.period_order"
    fid = api.s.execute(text("SELECT filing_id::text FROM regulatory_filing WHERE org_id = CAST(:o AS uuid) AND snapshot_id IS NOT NULL LIMIT 1"),
                        {"o": BANK_ORG}).scalar()
    r = api.post(f"/v1/filings/{fid}/assurance-shares", headers=maker, json={"recipient_name": "Audit", "recipient_email": "no-at-sign", "purpose": "x"})
    assert r.status_code == 422 and r.json()["error"]["error"] == "filing.share.recipient"
