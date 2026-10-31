"""Whose book a KRI set is on (E351): the rule the board opens on, the words it rests on, and the currency rule of the
filed trend — without a database (services.governance.kri_scope).
"""
from __future__ import annotations

from importlib import import_module

from services.governance import kri_scope as S

TOP, SUB, OTHER = "top", "sub", "other"


def _f(eid: str, role: str, name: str | None = None) -> dict:
    return {"entity_id": eid, "role": role, "name": name or eid}


def test_the_board_opens_on_the_report_at_the_head_of_the_group():
    group, own = _f(TOP, "consolidated"), _f(SUB, "solo")
    assert S.pick([group, own], {TOP}) == group
    # an undertaking at the head of a group reports for itself and for the group: the group's report opens
    assert S.pick([_f(TOP, "solo"), group, own], {TOP}) == group
    # no group at the top: the only filer, else a choice
    assert S.pick([own], {TOP}) == own
    assert S.pick([_f(TOP, "solo"), _f(OTHER, "solo")], {TOP, OTHER}) is None
    # two groups at the top: no one highest level of consolidation — the board asks which
    assert S.pick([group, _f(OTHER, "consolidated")], {TOP, OTHER}) is None
    # a sub-group's consolidated report is not the head's
    assert S.pick([_f(SUB, "consolidated"), _f(OTHER, "solo")], {TOP, OTHER}) is None
    assert S.pick([], {TOP}) is None


def test_every_kri_set_of_a_report_with_filer_rules_is_on_one_filers_book():
    """A report that gains filer rules and a KRI set cannot stay on the whole book unnoticed (the guard of E351)."""
    from services.governance.kri import _KRI_LABELS
    from services.governance.report_filers import RULES
    assert S.FRAMEWORKS == set(RULES) & set(_KRI_LABELS)
    assert set(S.HEAD) == set(S.FRAMEWORKS) == set(S.VERTICAL)


def test_the_default_rests_on_the_texts_words():
    for fw, (sentence, (rule, key, words)) in S.HEAD.items():
        quotes = import_module(f"services.governance.{rule}").QUOTES
        assert words in quotes[key][1], (fw, key)          # each QUOTES entry is checked against data/sources/legal
        assert "(" in sentence and sentence.endswith(")"), fw      # the legal reference closes it (the pop-up's)
    status, submitted, published, answer = S.QA["2023_6708"]
    assert (status, submitted, published) == ("Final", "30 Jan 2023", "25 Aug 2023")
    assert "highest level of consolidation in the EU" in answer and "highest level of consolidation in the EU" in S.HEAD["bank_p3esg"][0]
    assert S.QA["2022_6652"][0] == "Final"


def test_a_filed_money_figure_joins_the_trend_only_from_a_filing_in_euro():
    hist = [{"currency": "EUR", "total_value": 10, "figures": [{"fmt": "eur", "value": 5}, {"fmt": "pct", "value": 1.5}]},
            {"currency": "GBP", "total_value": 9, "value_at_risk": 3,
             "figures": [{"fmt": "eur", "value": 4}, {"fmt": "pct", "value": 2.5}]}]
    S.eur_only(hist)
    assert hist[0]["total_value"] == 10 and [f["value"] for f in hist[0]["figures"]] == [5, 1.5]
    assert hist[1]["total_value"] is None and hist[1]["value_at_risk"] is None
    assert [f["value"] for f in hist[1]["figures"]] == [None, 2.5]          # a share is the same in any currency


def test_a_filer_is_named_by_its_entity_and_its_report():
    assert S.label(_f(TOP, "consolidated", "Meridian Financial Group")) == "Meridian Financial Group (group)"
    assert S.label(_f(SUB, "solo", "Meridian Bank AG")) == "Meridian Bank AG"


def test_the_whole_book_reads_every_filing():
    assert S.history_filter(None) == ("", {})
