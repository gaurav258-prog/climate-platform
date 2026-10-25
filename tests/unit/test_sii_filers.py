"""Who reports Solvency II nat-cat risk (services.governance.sii_filers, E343): the reading in the acts' own words, and
the one gate every frozen book passes.

The end-to-end behaviour (calendar, scope, refresh, exports) is tests/integration/test_e2e_sii_filers.py.
"""
from __future__ import annotations

import ast
import inspect

from services.governance import filings, sii_filers
from services.reference import legal_texts as L


def test_every_reading_is_the_acts_own_wording():
    """Each quote is found word for word in the act it is from, as stored (data/sources/legal)."""
    assert len(sii_filers.QUOTES) == 6
    missing = [k for k, (celex, q) in sii_filers.QUOTES.items() if L.normalise(q) not in L.normalise(L.text(celex))]
    assert missing == []
    assert sii_filers.UNDERTAKING["template"] in sii_filers.QUOTES["ITS Art. 19(1)(s)(i)"][1].replace("S. ", "S.")
    assert sii_filers.GROUP["template"] in sii_filers.QUOTES["ITS Art. 34(1)(s)"][1]


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
