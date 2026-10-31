"""An insurance undertaking at the head of a group owes its own ORSA beside the group's (E353): the reading in the
Directive's own words, the one key (entity, role) for the ORSA's filing, figures and answers, and its calendar rule.

The end-to-end behaviour (calendar, documents page, answers, filings) is tests/integration/test_e2e_orsa_parent_own.py.
"""
from __future__ import annotations

import ast
import inspect
import re
from datetime import date
from pathlib import Path

from services.governance import (
    datapoint_catalog,
    filings,
    insurer_documents,
    irrd_filers,
    orsa_climate,
    orsa_filers,
    report_filers,
    template_answers,
)
from services.reference import legal_texts as L

ROOT = Path(__file__).resolve().parents[2]
ORSA = "insurer_orsa_climate"


def test_every_quote_is_the_stored_directive_s_own_wording():
    """Each reading is found word for word in the act it is from, as stored (data/sources/legal): Directive
    2009/138/EC (consolidated 17 Jan 2025), Directive (EU) 2025/2 (Art. 45(5), Art. 246(1) as it replaces them, its
    application date) and Delegated Regulation (EU) 2015/35."""
    missing = [k for k, (celex, q) in orsa_filers.QUOTES.items() if L.normalise(q) not in L.normalise(L.text(celex))]
    assert missing == []
    assert len(orsa_filers.QUOTES) == 12
    acts = {celex for celex, _ in orsa_filers.QUOTES.values()}
    assert acts == {"02009L0138-20250117", "32025L0002", "02015R0035-20241114"}
    # the readings the build rests on, each present
    q = {k: v[1] for k, v in orsa_filers.QUOTES.items()}
    assert "every insurance undertaking" in q["Directive 2009/138/EC Art. 45(1)"]
    assert "at the level of any subsidiary in the group" in q["Directive 2009/138/EC Art. 246(4), third subparagraph"]
    assert "remain responsible for its own compliance" in next(v for k, v in q.items() if k.startswith("Directive 2009/138/EC Art. 246(1)"))
    assert "annually" in next(v for k, v in q.items() if k.startswith("Directive 2009/138/EC Art. 45(5)"))
    assert "within 2 weeks after concluding the assessment" in q["Del. Reg. 2015/35 Art. 312(1)(b)"]
    assert "except for the ORSA supervisory report" in q["Del. Reg. 2015/35 Art. 373"]


def test_the_single_document_covers_the_group_and_its_subsidiaries_never_the_head_s_own():
    """Art. 246(4), third subparagraph, names the assessments a single document may cover: the group's and its
    subsidiaries'. The participating undertaking's own is not among them — so the rule's docstring says so, and no
    statement lets a group's document stand for its head's own ORSA."""
    third = orsa_filers.QUOTES["Directive 2009/138/EC Art. 246(4), third subparagraph"][1]
    assert "at the level of the group and at the level of any subsidiary in the group" in third
    assert "participating" not in third
    assert "single ORSA document does not cover the head's own assessment" in orsa_filers.__doc__


def test_the_q_and_a_record_names_each_answer_with_its_status_and_date():
    assert orsa_filers.QA["checked"] == ["2026-10-29", "2026-10-31"]
    for qid, (status, submitted, gist) in orsa_filers.QA["read"].items():
        assert qid.isdigit() and status in ("Final", "Revised") and re.fullmatch(r"\d\d \w{3} \d{4}", submitted) and gist
    assert orsa_filers.QA["read"]["1350"][:2] == ("Final", "05 Dec 2018")
    assert "the undertaking decides when to perform the regular ORSA" in orsa_filers.QA["read"]["1350"][2]


def test_a_head_undertaking_is_offered_its_own_orsa_and_the_group_s(monkeypatch):
    """The ORSA takes nat-cat's filers as they are (sii_filers.choices), the head twice; the recovery plan keeps one
    scope per entity (the ultimate parent's plan is the group's, IRRD Art. 7(1))."""
    from services.governance import sii_filers
    twice = [{"entity_id": "p", "name": "Parent", "role": "consolidated"}, {"entity_id": "p", "name": "Parent", "role": "solo"},
             {"entity_id": "s", "name": "Sub", "role": "solo"}]
    monkeypatch.setattr(sii_filers, "choices", lambda session, org_id: twice)
    monkeypatch.setattr(sii_filers, "is_filer", lambda session, org_id: False)
    pe = date(2026, 12, 31)
    assert orsa_filers.choices(None, "o", ORSA, pe) == twice
    assert orsa_filers.owed(None, "o", ORSA, pe) == {("p", "consolidated"), ("p", "solo"), ("s", "solo")}
    assert report_filers.owed(None, "o", ORSA, pe) == {("p", "consolidated"), ("p", "solo"), ("s", "solo")}
    assert [(c["entity_id"], c["role"]) for c in irrd_filers.choices(None, "o", irrd_filers.FRAMEWORK, pe)] == [
        ("p", "consolidated"), ("s", "solo")]
    assert "sii_filers.choices" in inspect.getsource(orsa_filers.choices)             # reused, not copied


def test_the_orsa_is_one_entity_s_two_reports_in_every_key():
    """filings._OWN_BOOK holds the ORSA beside nat-cat: the filing's scope (_scope_role), its book (own_book_ids), every
    lookup by entity (_role_match), its stated values (ROLE_SCOPED_REPORTS) and its answers (template_answers.filing_role)
    are each read on (entity, role). The recovery plan is not one."""
    assert filings._OWN_BOOK == {"insurer_solvency", ORSA}
    assert filings._OWN_BOOK <= datapoint_catalog.ROLE_SCOPED_REPORTS
    assert irrd_filers.FRAMEWORK not in filings._OWN_BOOK
    sql = filings._role_match("rf", "ob.entity_id", "ob.filing_role")
    assert "rf.framework NOT IN ('insurer_orsa_climate', 'insurer_solvency')" in sql
    # answers: kept per role for the ORSA only
    assert insurer_documents.answer_role(ORSA, "e", "solo") == "solo"
    assert insurer_documents.answer_role(irrd_filers.FRAMEWORK, "e", "solo") is None
    assert insurer_documents.answer_role(ORSA, None, "whole_org") is None
    assert "filing_role IS NOT DISTINCT FROM" in template_answers._KEY


def _sql_strings(path: Path):
    src = path.read_text()
    tree = ast.parse(src)
    parts = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in ast.walk(n) if v is not n}
    for node in ast.walk(tree):
        if id(node) in parts:
            continue
        if isinstance(node, ast.JoinedStr) or (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            yield node.lineno, ast.get_source_segment(src, node) or ""


def test_no_orsa_query_matches_by_entity_without_its_role():
    """E353's guard. A head undertaking holds two live ORSA filings and two sets of answers: any SQL in services/ or api/
    that finds a filing by its entity must match its role (filings._role_match, which now tells the ORSA apart), and any
    that finds template answers by their entity must match their role — else its own ORSA reads the group's. A new
    query without it fails here."""
    by_entity = re.compile(r"entity_id\s+IS NOT DISTINCT FROM|entity_id\s*=\s*(?:CAST\()?:", re.I)
    skip = {"services/eudr/declaration_filing.py", "services/governance/esrs_comparatives.py"}   # one scope per entity
    bad = []
    for path in [*ROOT.glob("services/**/*.py"), *ROOT.glob("api/**/*.py")]:
        rel = str(path.relative_to(ROOT))
        for line, seg in _sql_strings(path):
            if not by_entity.search(seg):
                continue
            if re.search(r"\bregulatory_filing\b", seg) and rel not in skip and "_role_match(" not in seg:
                bad.append(f"{rel}:{line} (filing)")
            if re.search(r"\btemplate_answers\b", seg) and "filing_role" not in seg and "{_KEY}" not in seg:
                bad.append(f"{rel}:{line} (answers)")
    assert bad == [], bad
    # every reader of the ORSA's answers passes the role; the computed capital reads the book's role
    assert "role=answer_role(" in inspect.getsource(insurer_documents.freeze)
    assert "role=answer_role(" in inspect.getsource(insurer_documents.save)
    assert "book_role(entity_ids, value_weights)" in inspect.getsource(orsa_climate.compute)
    # the live document is built on the filing's own gate and book
    assert "_book_scope" in inspect.getsource(insurer_documents.live) and "_scope_role" in inspect.getsource(insurer_documents.live)


def test_the_orsa_is_owed_every_period_from_its_own_conclusion():
    """The calendar owes the ORSA (Art. 45(5) as replaced: annually) with no date of its own: its filing's conclusion
    plus two weeks (Art. 312(1)(b)); the group's on the same day as the undertaking's (Art. 373: not extended). Only the
    ORSA runs from its conclusion, as the database's check on a date-less obligation says."""
    assert filings.runs_from_conclusion(ORSA)
    assert not any(filings.runs_from_conclusion(f) for f in filings.FRAMEWORKS if f != ORSA)
    assert filings._due_date(ORSA, date(2026, 12, 31)) is None
    assert filings.due_for_filing(ORSA, date(2026, 12, 31), date(2027, 3, 31))[0] == date(2027, 4, 14)
    d = date(2027, 4, 14)
    assert report_filers.due(ORSA, d, "consolidated") == d == report_filers.due(ORSA, d, "solo")
    assert "runs_from_conclusion(framework)" in inspect.getsource(filings.ensure_filer_obligations)
    mig = (ROOT / "core/db/migrations/versions/orsa_parent_own_20261031.py").read_text()
    assert "CHECK (due_date IS NOT NULL OR framework = 'insurer_orsa_climate')" in mig
    assert irrd_filers.owed(None, "o", irrd_filers.FRAMEWORK, None) == {}             # the recovery plan stays off it
