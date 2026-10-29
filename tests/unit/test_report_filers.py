"""Who files each entity-scoped report (services.governance.report_filers, E349): every rule's reading in its act's own
words, every entity-scoped report under a rule, and the one gate every calendar, frozen book and export passes.

The end-to-end behaviour (calendar, scope, statements, exports) is tests/integration/test_e2e_report_filers.py.
"""
from __future__ import annotations

import ast
import inspect

from services.governance import (
    crr_filers,
    csrd_filers,
    filing_annex,
    filing_export,
    filings,
    report_filers,
    report_snapshots,
)
from services.reference import legal_texts as L
from services.supervision import deadlines


def test_every_reading_is_the_acts_own_wording():
    """Each rule's quotes are found word for word in the act they are from, as stored (data/sources/legal)."""
    for mod in {report_filers.rule(f) for f in report_filers.RULES}:
        missing = [k for k, (celex, q) in mod.QUOTES.items() if L.normalise(q) not in L.normalise(L.text(celex))]
        assert missing == [], mod.__name__
    assert len(crr_filers.QUOTES) == 7 and len(csrd_filers.QUOTES) == 7
    assert "449a" in crr_filers.QUOTES["CRR Art. 13(1), second subparagraph"][1]      # added by Regulation (EU) 2024/1623


def test_every_entity_scoped_report_names_its_filers():
    """No entity-scoped report keeps the framework-blind whole-organisation default: each has a filer rule, except the
    ESRS statement (its own scope: services.governance.esrs_statement, on the same CSRD roles) and the insurer documents
    (who files them waits on the Solvency II Directive and the IRRD, not yet held — docs/ENGINEERING_PROCESS.md E349)."""
    own_scope = {"esrs_pack", "insurer_orsa_climate", "insurer_recovery_stress"}
    assert filings._ENTITY_SCOPED - own_scope == set(report_filers.RULES)
    for f in report_filers.RULES:
        if f == "insurer_solvency":
            continue
        b = report_filers.rule(f).BASIS[f]
        assert {"who", "title", "shows", "legal", "organisation"} <= set(b), f
        assert report_filers.scope_basis(f)["legal"] == b["legal"]


def test_a_whole_organisation_book_without_its_filer_exports_no_template():
    whole = {"_scope": {"reporting_entity_id": None}}
    for f in ("bank_p3esg", "bank_tcfd", "reit_taxonomy"):
        code, params = report_filers.export_refusal(f, whole, "whole_org")
        assert code == "filing.refused.whole_org_frozen" and params["report"] == filings.FRAMEWORKS[f]["label"]
        assert report_filers.export_refusal(f, {**whole, "_filer": {"level": "organisation"}}, "whole_org") is None
        assert report_filers.export_refusal(f, {"_scope": {"reporting_entity_id": "e1"}}, "solo") is None
    assert report_filers.export_refusal("insurer_solvency", whole, "whole_org") == ("filing.refused.sii_whole_org_frozen", {})
    assert report_filers.export_refusal("sfdr_pai", whole, "whole_org") is None              # filed for the organisation


def _calls(fn) -> set[str]:
    return {n.func.id if isinstance(n.func, ast.Name) else n.func.attr for n in ast.walk(ast.parse(inspect.getsource(fn)))
            if isinstance(n, ast.Call) and isinstance(n.func, (ast.Name, ast.Attribute))}


def test_every_calendar_book_and_export_passes_the_filer_rule():
    """The calendar owes a ruled report through ensure_filer_obligations (also when a supervisor publishes a date); the
    pre-filing check, generate, refresh and restate get a book only through _book_scope, which refuses a
    whole-organisation scope that is no filer's; every frozen book of a ruled report records its filer; every export
    but the JSON record asks export_refusal; the official form says who reports."""
    assert "ensure_filer_obligations" in _calls(filings.ensure_obligations) and "governs" in _calls(filings.ensure_obligations)
    assert "ensure_filer_obligations" in _calls(filings.ensure_sii_obligations)
    assert "owed" in _calls(filings.ensure_filer_obligations)
    assert {"governs", "ensure_filer_obligations"} <= _calls(deadlines._propagate)
    assert "whole_org_refusal" in _calls(filings._book_scope) and "whole_org_refusal" in _calls(filings.preflight)
    assert "exempt_refusal" in _calls(filings._check_scope)
    assert {"governs", "record"} <= _calls(report_snapshots.create_snapshot)
    assert "export_refusal" in _calls(filing_export.export_filing)
    assert {"section", "statement_section"} <= _calls(filing_annex._build_annex)
    # the Taxonomy reports and the ESRS statement read the same undertakings
    assert "undertakings" in _calls(filings._ensure_esrs_obligations)


def test_a_groups_pillar3_form_states_each_subsidiarys_size_class():
    payload = {"_filer": {"level": "group", "entity_id": "g", "subsidiaries": [
        {"entity_id": "a", "name": "Alpha Bank", "stated": "large", "attested_by": "checker@x"},
        {"entity_id": "b", "name": "Beta Leasing", "stated": None, "attested_by": None}]}}
    sec = crr_filers.statement_section(payload)
    assert sec["title"] == "Large subsidiaries" and [r["cells"][0]["text"] for r in sec["rows"]] == ["Alpha Bank", "Beta Leasing"]
    cell = sec["rows"][0]["cells"][1]
    assert cell["supply"] == {"framework": "bank_p3esg", "key": "large_institution", "member": "a", "choices": crr_filers.CHOICES}
    assert cell["frozen_value"] == "large" and "Not stated: Beta Leasing" in sec["note"]
    assert crr_filers.statement_section({"_filer": {"level": "institution"}}) is None
    # the statement's choices are the catalog's
    from services.governance.datapoint_catalog import CATALOG
    dp = next(d for d in CATALOG["bank_p3esg"] if d["key"] == crr_filers.KEY)
    assert dp["choices"] == crr_filers.CHOICES and dp["breakdown"] == "subsidiary" and dp["lane"] == "provided"


def test_the_who_reports_section():
    assert report_filers.section("bank_p3esg", {"_scope": {"reporting_entity_id": None}})["note"].startswith("Not exported")
    sec = report_filers.section("bank_tcfd", {"_filer": {"level": "group", "entity_id": "g", "name": "G", "basis": "Art. 29a"}})
    assert sec["rows"][0]["cells"][1]["text"] == report_filers.LEVELS["group"] and "note" not in sec
    assert report_filers.section("insurer_solvency", {"_scope": {"reporting_entity_id": None}}) is None    # its own form says it
    assert report_filers.section("sfdr_pai", {}) is None


def test_no_dated_entity_scoped_report_falls_back_to_the_whole_organisation():
    """The calendar has no framework-blind default any more (ensure_obligations): an entity-scoped report with a calendar
    deadline is owed through its filer rule — a new one without a rule fails here before it can owe the whole book."""
    from datetime import date
    for f in filings._ENTITY_SCOPED - {"esrs_pack"}:
        if filings._due_date(f, date(2025, 12, 31)) is not None:
            assert report_filers.governs(f), f
    src = inspect.getsource(filings.ensure_obligations)
    assert "requires_solo_filing" not in src and "'solo'" not in src
