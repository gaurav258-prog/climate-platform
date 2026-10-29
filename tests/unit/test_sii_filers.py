"""Who reports Solvency II nat-cat risk (services.governance.sii_filers, E343, E348): the reading in the acts' own words,
the regulator's Q&A on record, the one gate every frozen book passes, and an entity's two reports kept apart by role.

The end-to-end behaviour (calendar, scope, refresh, exports) is tests/integration/test_e2e_sii_filers.py.
"""
from __future__ import annotations

import ast
import inspect

from services.governance import filings, sii_filers
from services.reference import legal_texts as L


def test_every_reading_is_the_acts_own_wording():
    """Each quote is found word for word in the act it is from, as stored (data/sources/legal)."""
    assert len(sii_filers.QUOTES) == 15
    missing = [k for k, (celex, q) in sii_filers.QUOTES.items() if L.normalise(q) not in L.normalise(L.text(celex))]
    assert missing == []
    assert sii_filers.UNDERTAKING["template"] in sii_filers.QUOTES["ITS Art. 19(1)(s)(i)"][1].replace("S. ", "S.")
    assert sii_filers.GROUP["template"] in sii_filers.QUOTES["ITS Art. 34(1)(s)"][1]
    # the two duties' subjects (E348): every insurance undertaking for itself; the participating undertaking for its group
    assert sii_filers.QUOTES["ITS Art. 19(1)"][1].startswith("Insurance and reinsurance undertakings")
    assert sii_filers.QUOTES["ITS Art. 34(1)"][1].startswith("Participating insurance and reinsurance undertakings")
    # the group's deadline: Art. 312(1)(c)'s 14 weeks, extended by the weeks Art. 373 says
    assert "14 weeks" in sii_filers.QUOTES["Del. Reg. Art. 312(1)(c)"][1]
    assert f"extended by {sii_filers.GROUP_EXTRA_WEEKS} weeks" in sii_filers.QUOTES["Del. Reg. Art. 373, 6 weeks"][1]


def test_the_regulators_qa_is_on_record():
    """Each EIOPA Q&A the reading rests on is recorded with its status and date of submission, and the check's dates."""
    import re
    assert sii_filers.QA["checked"] and all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) for d in sii_filers.QA["checked"])
    for qid, (status, submitted, reading) in sii_filers.QA["read"].items():
        assert qid.isdigit() and status in ("Final", "Revised") and re.fullmatch(r"\d{2} [A-Z][a-z]{2} \d{4}", submitted), qid
        assert reading


def test_a_groups_report_is_due_six_weeks_after_an_undertakings():
    from datetime import date
    d = date(2026, 4, 8)
    assert sii_filers.due(d, "solo") == d and sii_filers.due(d, "whole_org") == d
    assert sii_filers.due(d, "consolidated") == date(2026, 5, 20) and sii_filers.due(None, "consolidated") is None
    # the rule a group's filing shows: the calendar's weeks for an undertaking (its mandate) plus Art. 373's
    weeks = filings._mandate_of(sii_filers.FRAMEWORK)["deliverable"]["due"]["weeks_after_period_end"]
    assert f"{weeks + sii_filers.GROUP_EXTRA_WEEKS} weeks after financial year end" in sii_filers.GROUP_DUE_RULE


def test_an_entitys_own_book_is_read_from_its_own_book_ids_only():
    """role 'solo' freezes the entity's own book (itself and its branches) unweighted; every other entity scope its subtree."""
    src = inspect.getsource(filings._book_basis)
    assert "_E.own_book_ids if role == \"solo\" else _E.subtree_ids" in src and "role != \"solo\" and len(entity_ids) > 1" in src
    assert "_scope_role" in _calls(filings._book_scope)
    assert filings._OWN_BOOK == {"insurer_solvency"}


def _sql_strings(path):
    """Every string in a module with its line — f-strings as written, so a {_role_match(...)} in one is seen."""
    import ast
    src = path.read_text()
    tree = ast.parse(src)
    parts = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in ast.walk(n) if v is not n}
    for node in ast.walk(tree):
        if id(node) in parts:                                   # a piece of an f-string: read with the whole
            continue
        if isinstance(node, ast.JoinedStr) or (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            yield node.lineno, ast.get_source_segment(src, node) or ""


# looked up by entity, but only ever for one report type, which no entity holds twice (filings._OWN_BOOK)
_ONE_SCOPE_PER_ENTITY = {"services/eudr/declaration_filing.py": "EUDR due-diligence statements",
                         "services/governance/esrs_comparatives.py": "ESRS statements"}


def test_every_filing_found_by_its_entity_is_found_by_its_role_too():
    """E348's guard: a parent holds two live Solvency II nat-cat filings — its own and its group's — so any query that
    finds a filing (or matches one to an obligation) by its entity must match its role too (filings._role_match), or it
    mixes an undertaking's own report with its group's: the calendar, the live-filing rule, the previous period, the
    comparison, the siblings. A new such query without it fails here."""
    import re
    from pathlib import Path
    lookup = re.compile(r"entity_id\s+IS NOT DISTINCT FROM|entity_id\s*=\s*(?:CAST\()?:", re.I)
    root = Path(__file__).resolve().parents[2]
    bad = []
    for path in [*root.glob("services/**/*.py"), *root.glob("api/**/*.py")]:
        rel = str(path.relative_to(root))
        if rel in _ONE_SCOPE_PER_ENTITY:
            continue
        for line, seg in _sql_strings(path):
            if re.search(r"\bregulatory_filing\b", seg) and lookup.search(seg) and "_role_match(" not in seg:
                bad.append(f"{rel}:{line}")
    assert bad == [], bad
    # the rule itself: only a report an entity can hold twice is told apart by role; a whole-organisation scope or a
    # filing from before roles were stamped by its entity alone
    sql = filings._role_match("rf", "ob.entity_id", "ob.filing_role")
    assert "rf.framework NOT IN ('insurer_solvency')" in sql and "ob.entity_id IS NULL" in sql and "rf.filing_role IS NULL" in sql


def test_a_whole_organisation_book_without_its_filer_exports_no_template():
    whole = {"_scope": {"reporting_entity_id": None}}
    assert sii_filers.export_refusal(whole, "whole_org") == ("filing.refused.sii_whole_org_frozen", {})
    assert sii_filers.unrecorded_whole_org(whole) and sii_filers.unrecorded_whole_org({})
    recorded = {**whole, "_filer": {"level": "undertaking", "entity_id": None, **sii_filers.UNDERTAKING}}
    assert sii_filers.export_refusal(recorded, "whole_org") is None
    # an entity's or a group's book is not a whole-organisation one: E342's group refusals speak for a group
    assert sii_filers.export_refusal({"_scope": {"reporting_entity_id": "e1"}}, "solo") is None
    assert not sii_filers.unrecorded_whole_org({"_scope": {"reporting_entity_id": None}, "_group_solvency": {"status": "complete"}})


def _calls(fn) -> set[str]:
    return {n.func.id for n in ast.walk(ast.parse(inspect.getsource(fn))) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def test_every_frozen_book_passes_the_filer_gate():
    """The pre-filing check, generate, refresh and restate get a book only through _book_scope, which refuses a
    whole-organisation scope that is no filer's; _book_basis is called nowhere else."""
    src = inspect.getsource(filings)
    assert src.count("_book_basis(") == 2                       # its definition and _book_scope's call
    assert "_book_basis" in _calls(filings._book_scope) and "whole_org_refusal" in _calls(filings._book_scope)
    assert "_book_scope" in _calls(filings._freeze) and "_book_scope" in _calls(filings._summary_for)
    for fn in (filings.generate_filing, filings.refresh_filing, filings.restate_filing):
        assert "_freeze" in _calls(fn), fn.__name__
    assert "_summary_for" in _calls(filings.preflight)
    # the calendar's Solvency II obligations come from the filers, not the blanket whole-organisation row
    assert "ensure_sii_obligations" in _calls(filings.ensure_obligations)
