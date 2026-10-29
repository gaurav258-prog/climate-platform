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
    irrd_filers,
    orsa_filers,
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
    assert len(crr_filers.QUOTES) == 7 and len(csrd_filers.QUOTES) == 7 and len(orsa_filers.QUOTES) == 8
    assert len(irrd_filers.QUOTES) == 6
    assert "449a" in crr_filers.QUOTES["CRR Art. 13(1), second subparagraph"][1]      # added by Regulation (EU) 2024/1623


def test_every_entity_scoped_report_names_its_filers():
    """No entity-scoped report keeps the framework-blind whole-organisation default: each has a filer rule, except the
    ESRS statement (its own scope: services.governance.esrs_statement, on the same CSRD roles)."""
    own_scope = {"esrs_pack"}
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


def test_the_orsa_is_reported_by_the_undertakings_and_groups_of_solvency_ii():
    """The ORSA's filers are nat-cat's — each undertaking (Art. 304(1)(c)) and the group (Art. 372(1)) — read once, in
    sii_filers; the documents API refuses the whole organisation as the filing does."""
    import api.routers.insurer_documents as docs
    assert "choices" in _calls(orsa_filers.choices) and "sii_filers" in inspect.getsource(orsa_filers.choices)
    assert "_filer_or_refuse" in _calls(docs.get_document) and "_filer_or_refuse" in _calls(docs.put_answers)
    assert "whole_org_refusal" in _calls(docs._filer_or_refuse)
    assert report_filers.scope_basis("insurer_orsa_climate")["title"] == "Who reports the ORSA"
    assert "sii_filers" in inspect.getsource(irrd_filers.choices) and irrd_filers.owed(None, "o", "f", None) == {}


def test_the_insurer_document_specs_quote_their_directives_word_for_word():
    """The ORSA climate analysis and the recovery plan templates (regspec sii_climate / irrd_recovery) were captured from
    the OJ texts of Directives (EU) 2025/2 and 2025/1; now that both are stored, every item's wording and every quote is
    found word for word in them (as E342 does for ITS 2023/894)."""
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "data" / "reference" / "regspec"

    def quotes(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "quote" and isinstance(v, str):
                    yield v
                else:
                    yield from quotes(v)
        elif isinstance(o, list):
            for v in o:
                yield from quotes(v)
    for spec, celex in (("sii_climate/dir_2025_2.json", "32025L0002"), ("irrd_recovery/dir_2025_1.json", "32025L0001")):
        d = json.loads((root / spec).read_text())
        text = L.normalise(L.text(celex))
        wording = [i["label"] for t in d["templates"] for i in t["items"] if i["kind"] != "heading"] + list(quotes(d))
        assert len(wording) >= 9 and [w for w in wording if L.normalise(w) not in text] == [], spec


def test_the_insurer_documents_offer_one_scope_per_entity(monkeypatch):
    """Solvency II nat-cat offers a parent undertaking twice — its group's report and its own (E348, filings._OWN_BOOK);
    the ORSA and the recovery plan take the same filers one scope per entity, the group's first: an entity's own book
    beside its group's is nat-cat's scope only, and the ultimate parent's plan is the group's (IRRD Art. 7(1))."""
    from services.governance import sii_filers
    twice = [{"entity_id": "p", "name": "Parent", "role": "consolidated"}, {"entity_id": "p", "name": "Parent", "role": "solo"},
             {"entity_id": "s", "name": "Sub", "role": "solo"}]
    monkeypatch.setattr(sii_filers, "choices", lambda session, org_id: twice)
    for mod in (orsa_filers, irrd_filers):
        assert [(c["entity_id"], c["role"]) for c in mod.choices(None, "o", mod.FRAMEWORK, None)] == [("p", "consolidated"), ("s", "solo")]
    assert "insurer_orsa_climate" not in filings._OWN_BOOK and "insurer_recovery_stress" not in filings._OWN_BOOK
