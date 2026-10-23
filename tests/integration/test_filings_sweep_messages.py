"""Filings, funds, the auditor's share, contracts and exchange rates speak in the message catalogue's words (UI standard,
product owner 2026-10-16) — the final sweep of these screens and the server text they show.

A refused package, a refused holdings row, a share that no longer serves its pack, a refused contract, third party or
insurer document used to reach the screen as the exception's own sentence (str(e)) or a sentence written in the router —
'4-eyes violation: checker (…) cannot be the same as maker', 'each holding needs market_value_eur, or market_value +
currency', '… (report type esrs_pack; /v1/esrs)'. A holdings row the model refused answered FastAPI's own list, which no
screen reads, so the customer saw only "Could not add the holdings". Each is now a catalogue code (prefix filings., or an
existing one reused) with its values; the frozen records keep their codes and the form names them. These tests hold that
on the code and through the API.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from sqlalchemy import text

from core import messages
from core.errors import UserError
from scripts import ui_language as U
from tests.integration.conftest import login as _login
from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
CODED = {"UserError", "FilingError", "ShareClassError", "AnswerError", "ContractError", "DocumentError", "ThirdPartyError"}
FILES = ["api/routers/filings.py", "api/routers/packages.py", "api/routers/funds.py", "services/funds/holding.py",
         "services/funds/onboarding.py", "services/funds/registry.py", "api/routers/insurer_documents.py",
         "api/routers/contracts.py", "api/routers/grc_followups.py", "services/eet/share_classes.py",
         "services/governance/report_snapshots.py", "services/governance/contracts.py",
         "services/governance/insurer_documents.py", "services/intelligence/third_parties.py"]
# the routers of this sweep refuse only through the catalogue
ROUTERS = ["api/routers/packages.py", "api/routers/grc_followups.py", "api/routers/contracts.py",
           "api/routers/insurer_documents.py"]
SAMPLE = dict(organisation="Meridian Bank (demo)", isin="DE0007164600", basis="turnover", parts="12.5", aligned="10",
              max=180, limit=25, what="An answer", n=2, first="A first answer", report="Pillar 3 ESG", on="31 Dec 2025",
              first_date="1 Jan 2026", kinds="data centre, cloud provider", levels="critical, important, standard")


def _coded_calls(path: Path):
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Call) and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            code = n.args[0].value
            if name in CODED | {"render", "label"} and re.fullmatch(r"[a-z]+(\.[a-z_]+)+", code):
                yield code, n.lineno
        if isinstance(n, ast.Dict):          # a code map (grc_followups.GONE)
            for v in n.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str) and v.value.startswith("filings."):
                    yield v.value, v.lineno


def test_every_code_these_files_raise_or_render_is_in_the_catalogue():
    known = set(messages.catalogue())
    missing = [f"{f}:{line} {code}" for f in FILES if (ROOT / f).exists() for code, line in _coded_calls(ROOT / f)
               if code not in known]
    assert missing == [], f"Add these codes to data/reference/messages.en.json: {missing}"


def test_every_filings_message_renders_in_customer_words():
    """Each filings.* code fills with its values (no {placeholder} left), has a label of at most eight words, and says
    nothing internal — in its label or in any part of its detail."""
    codes = [c for c in messages.catalogue() if c.startswith("filings.")]
    assert codes
    bad = []
    for code in codes:
        r = messages.render(code, **SAMPLE)
        if len(r["label"].split()) > 8:
            bad.append(f"{code}: label too long")
        for part in [r["label"], *r["detail"].values()]:
            if "{" in part or U.INTERNAL.search(part):
                bad.append(f"{code}: {part[:80]}")
    assert bad == []


def test_the_routers_of_this_sweep_refuse_only_through_the_catalogue():
    """No HTTPException — its detail was a sentence written in the router, or the exception's own text."""
    used = [f"{f}:{n.lineno}" for f in ROUTERS for n in ast.walk(ast.parse((ROOT / f).read_text(encoding="utf-8")))
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "HTTPException"]
    assert used == []


def test_a_refused_holdings_row_names_the_row_in_customer_words(api):
    """A row the holdings model refuses answers the catalogue's message — the label, and the row's ISIN in its detail —
    not FastAPI's list of validation errors, which no screen reads."""
    h = _login(api, "admin@nordkap.demo", "Demo!admin1")
    fund = api.s.execute(text("""SELECT f.fund_id::text FROM funds f JOIN organizations o ON o.org_id = f.org_id
                                 WHERE o.name LIKE 'Nordkap%' LIMIT 1""")).scalar()
    r = api.post(f"/v1/funds/{fund}/holdings", headers=h, json={"holdings": [
        {"isin": "US0378331005", "market_value_eur": 5_000_000}, {"isin": "DE0007164600"}]})
    body = r.json()["error"]
    assert r.status_code == 422 and body["error"] == "filings.holding.no_value"
    assert body["message"] == "A holding has no market value" and "DE0007164600" in body["detail"]["what"]
    r = api.post(f"/v1/funds/{fund}/holdings", headers=h, json={"holdings": [
        {"isin": "US0378331005", "market_value_eur": 5_000_000, "revenue": 3.8e11}]})
    assert r.status_code == 422 and r.json()["error"]["error"] == "filings.holding.financials_currency"
    r = api.post(f"/v1/funds/{fund}/holdings", headers=h, json={"holdings": [
        {"isin": "US0378331005", "market_value_eur": 5_000_000, "taxonomy_aligned_capex_pct": 10, "taxonomy_nuclear_aligned_capex_pct": 12.5}]})
    body = r.json()["error"]
    assert body["error"] == "filings.holding.taxonomy_parts_exceed" and "CapEx" in body["detail"]["what"] and "12.5%" in body["detail"]["what"]


def test_the_auditors_share_speaks_in_customer_words(api):
    """The public page of a share names the report (never its internal code), says what the pack holds, and — once the
    share no longer serves it — why, in the catalogue's words; an unknown link and a refused download are catalogue
    refusals."""
    from services.governance.admin_view import report_name
    r = api.get("/v1/assurance/not-a-share-we-know")
    assert r.status_code == 404 and r.json()["error"]["error"] == "filings.share.unknown"
    maker = _login(api, "admin@meridian.demo", "Demo!admin1")
    fid, fw = api.s.execute(text("""SELECT filing_id::text, framework FROM regulatory_filing
                                    WHERE org_id = CAST(:o AS uuid) AND snapshot_id IS NOT NULL LIMIT 1"""), {"o": BANK_ORG}).first()
    made = api.post(f"/v1/filings/{fid}/assurance-shares", headers=maker,
                    json={"recipient_name": "An auditor", "recipient_email": "auditor@example.com", "purpose": "Limited assurance"})
    assert made.status_code == 201, made.text
    token = made.json()["link"].rsplit("/", 1)[1]
    d = api.get(f"/v1/assurance/{token}").json()
    assert d["status"] == "active" and d["state"] is None and d["report"] == report_name(fw) and "_" not in d["report"]
    assert d["contents"]["code"] == "filings.share.contents" and not U.INTERNAL.search(str(d["contents"]))
    assert api.post(f"/v1/assurance-shares/{made.json()['share_id']}/revoke", headers=maker).status_code == 200
    d = api.get(f"/v1/assurance/{token}").json()
    assert d["status"] == "revoked" and d["state"]["code"] == "filings.share.revoked" and d["organisation"] in d["state"]["detail"]["what"]
    r = api.get(f"/v1/assurance/{token}/download.zip")
    assert r.status_code == 410 and r.json()["error"]["error"] == "filings.share.revoked"


def test_a_refused_package_is_the_catalogues_refusal():
    from fastapi.testclient import TestClient

    from api.main import app
    r = TestClient(app).get("/v1/packages/00000000-0000-0000-0000-000000000000/xbrl")
    body = r.json()["error"]
    assert r.status_code == 410 and body["error"] == "filings.package.retired" and not U.INTERNAL.search(str(body))


def test_a_report_the_platform_cannot_freeze_is_refused_with_a_code(session_rolled_back):
    """create_snapshot refuses an unknown or retired report type as the catalogue's refusal — still a ValueError for its
    callers."""
    from services.governance.filings import FilingError
    from services.governance.report_snapshots import create_snapshot
    with pytest.raises(FilingError) as refused:
        create_snapshot(session_rolled_back, BANK_ORG, "no_such_report", None, period_end="2025-12-31")
    assert refused.value.code == "filing.refused.unknown_report" and isinstance(refused.value, ValueError)
    with pytest.raises(FilingError) as refused:
        create_snapshot(session_rolled_back, BANK_ORG, "reit_tcfd", None, period_end="2025-12-31")
    assert refused.value.code.startswith("filing.refused.retired")


def test_the_form_names_where_each_rate_came_from_and_who_signed_the_rules():
    """The frozen currency and consolidation records keep their codes (source 'ecb', role 'regulatory'); the form the
    screen reads names each — every source and role the platform records has a name."""
    from api.routers.filings import _named
    from services.intake.money import _FX_SOURCES
    from services.regspec.signoff import ROLES
    v = _named({"fx": {"rates_used": [{"source": s} for s in (*_FX_SOURCES, None)]},
                "consolidation": {"signoff": {"signed": [{"role": r} for r in ROLES]}}})
    labels = [r["source_label"] for r in v["fx"]["rates_used"]] + [g["role_label"] for g in v["consolidation"]["signoff"]["signed"]]
    assert all(lab and "_" not in lab for lab in labels), labels
    assert v["fx"]["rates_used"][-1]["source_label"] == messages.label("filings.fx.source_unknown")


def test_the_holdings_model_refuses_through_the_catalogue():
    """The model itself refuses (a look-through's constituents are Holdings too), so every path that builds one does."""
    from services.funds.holding import Holding
    with pytest.raises(UserError) as refused:
        Holding(isin="US0000000001")
    assert refused.value.code == "filings.holding.no_value" and refused.value.params == {"isin": "US0000000001"}
    with pytest.raises(UserError) as refused:
        Holding(isin="US0000000001", market_value_eur=1.0, taxonomy_fossil_gas_aligned_pct=2.0)
    assert refused.value.code == "filings.holding.taxonomy_parts_alone" and refused.value.params["basis"] == "turnover"


def test_contracts_third_parties_and_insurer_documents_refuse_in_customer_words(api):
    h = _login(api, "admin@meridian.demo", "Demo!admin1")
    r = api.post("/v1/contracts", headers=h, files={"file": ("empty.pdf", b"", "application/pdf")}, data={"title": "An agreement"})
    assert r.status_code == 400 and r.json()["error"]["error"] == "filings.contract.empty"
    r = api.post("/v1/third-parties", headers=h, json={"name": "A provider", "kind": "nonsense", "latitude": 50.1, "longitude": 8.7})
    assert r.status_code == 422 and r.json()["error"]["error"] == "filings.third_party.kind" and "_" not in r.json()["error"]["detail"]["what"]
    assert api.get("/v1/insurance/documents/no_such_document", headers=h).json()["error"]["error"] == "error.not_found"
    ins = _login(api, "admin@iberia.demo", "Demo!admin1")
    r = api.put("/v1/insurance/documents/insurer_orsa_climate/answers", headers=ins,
                json={"answers": {"impact.interval": {"text": "5 years"}}, "entity_id": "496937e3-ea3c-4597-9066-c98cc1c2f742"})
    assert r.status_code == 422 and r.json()["error"]["error"] == "filings.insurer_doc.interval"
