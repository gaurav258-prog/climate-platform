"""How often an institution discloses its ESG risks (services.governance.crr_frequency, E354): every reading in the act's
own words, the rule for every size class and listing, the half-year deadline the mandate dates it by, and the Q&A record.

The calendar, the scope and the exports end to end: tests/integration/test_e2e_p3_semiannual.py.
"""
from __future__ import annotations

import pytest

from services.governance import crr_filers
from services.governance import crr_frequency as CF
from services.reference import legal_texts as L


def test_every_reading_is_the_acts_own_wording():
    missing = [k for k, (celex, q) in CF.QUOTES.items() if L.normalise(q) not in L.normalise(L.text(celex))]
    assert missing == []
    assert len(CF.QUOTES) == 24
    # every table and template, qualitative and quantitative, at each date; populated by the CRR's frequency (ITS 2024/3172)
    assert "(a) qualitative information" in CF.QUOTES["ITS 2024/3172 Art. 22(1)"][1]
    assert "Articles 433a, 433b and 433c" in CF.QUOTES["ITS 2024/3172 Art. 26(2)"][1]
    assert {c for c, _ in CF.QUOTES.values()} == {"02013R0575-20250101", "32024R3172", "32026R0722", "32013L0050"}
    # the semi-annual list names Article 449a (added by Regulation (EU) 2024/1623); the derogation spares no G-SII
    assert CF.QUOTES["CRR Art. 433a(1)(b)(xv)"][1] == "(xv) Article 449a;"
    assert "other than G-SIIs that are non-listed" in CF.QUOTES["CRR Art. 433a(2)"][1]
    assert "Article 449a on an annual basis" in CF.QUOTES["CRR Art. 433b(2)"][1]
    # the half-yearly report's six months and its latest date, as Directive 2013/50/EU replaced them
    td = CF.QUOTES["Directive 2004/109/EC Art. 5(1), as replaced by Directive 2013/50/EU"][1]
    assert "first six months of the financial year" in td and "three months thereafter" in td


@pytest.mark.parametrize("size, listing, want, needs", [
    ("gsii", None, "semiannual", []),                 # Art. 433a(1): a G-SII, listed or not — no listing needed
    ("gsii", "non_listed", "semiannual", []),         # the derogation of Art. 433a(2) is for 'other than G-SIIs'
    ("large", "listed", "semiannual", []),            # Art. 433a(1)(b)(xv)
    ("large", "non_listed", "annual", []),            # Art. 433a(2)
    ("large", None, None, ["listing"]),               # a large institution other than a G-SII: its listing decides
    ("not_large", None, "annual", []),                # Arts 433b, 433c: annual, listed or not
    ("not_large", "listed", "annual", []),
    (None, None, None, ["size", "listing"]),
    (None, "listed", None, ["size"]),
])
def test_the_frequency_of_each_size_class_and_listing(size, listing, want, needs):
    f = CF.frequency(size, listing)
    assert (f["frequency"], f["needs"]) == (want, needs)
    assert (f["basis"] is None) == (want is None)


def test_an_unknown_size_class_is_refused():
    with pytest.raises(ValueError):
        CF.frequency("medium", "listed")


def test_the_statements_offer_the_rules_choices():
    assert set(crr_filers.CHOICES) == {CF.GSII, CF.LARGE, CF.NOT_LARGE}
    assert set(crr_filers.LISTINGS) == {CF.LISTED, CF.NON_LISTED}
    assert crr_filers.LARGE_SIZES == {CF.GSII, CF.LARGE}
    # screen words carry no legal citation (they are in the catalog note, shown in a pop-up)
    assert not any("Art." in w for w in [*crr_filers.CHOICES.values(), *crr_filers.LISTINGS.values()])


def test_the_half_year_is_dated_by_the_half_yearly_reports_latest_date():
    """The mandate dates a half-year three months after it — the Transparency Directive's latest date for the half-yearly
    financial report, as the annual disclosure is dated by the annual report's four months — a planning date."""
    from datetime import date

    from services.governance.filings import due_for
    from services.supervision.mandates import registry
    m = next(x for x in registry()["mandates"] if x["id"] == "crr_449a_pillar3_esg")
    hy = m["deliverable"]["due"]["half_year"]
    assert hy["months_after_period_end"] == 3 and "planning date" in hy["ref"] and "2013/50/EU" in hy["ref"]
    assert due_for("bank_p3esg", date(2026, 6, 30), half_year=True)[0] == date(2026, 9, 30)
    assert due_for("bank_p3esg", date(2026, 12, 31))[0] == date(2027, 4, 30)          # the annual rule, unchanged
    assert due_for("bank_tcfd", date(2026, 6, 30), half_year=True) == (None, None)     # no half-year for the Taxonomy


def test_the_regulators_qa_is_recorded_with_status_and_date():
    doc = CF.__doc__
    for qa in ("2022_6444 (final, submitted 10 May 2022, published 30 Jun 2023)", "2024_7126 (rejected 7 Jan 2025)",
               "2025_7567 (rejected 26 Sep 2025)", "checked 2026-10-31"):
        assert qa in doc
