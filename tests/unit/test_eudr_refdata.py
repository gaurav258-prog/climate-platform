"""EUDR reference data: every quote is in its stored official text; counts, scope() and country_risk() as printed."""
from datetime import date

import pytest

from services.reference import eudr_refdata as R
from services.reference import legal_texts as L


def _in(celex: str, quote: str) -> bool:
    return L.normalise(quote) in L.normalise(L.text(celex))


ANNEX = R._annex()
CC = R._countries()


@pytest.mark.parametrize("v", ANNEX["versions"], ids=lambda v: v["id"])
def test_every_annex_quote_is_in_its_source_text(v):
    src = v["source_celex"]
    for e in v["entries"]:
        assert _in(src, e["description"]), (e["code"], e["description"])
        for n in e["notes"]:
            assert _in(src, n), (e["code"], n)
        if e.get("applies_from_quote"):
            assert _in(src, e["applies_from_quote"]), e["code"]
        if e["printed_code"]:
            assert _in(src, e["printed_code"] + " " + e["description"]), e["code"]   # code printed with its text
    for g in v["general_exclusions"]:
        assert _in(src, g["text"])
    for n in v["commodity_notes"].values():
        assert _in(src, n)
    for q, c in zip(v["date_basis"]["quotes"], v["date_basis"]["quote_celex"]):
        assert _in(c, q), q
    if "change" in v:
        assert _in(v["change"]["celex"], v["change"]["quote"])


def test_ambiguities_and_country_quotes_are_in_the_texts():
    for a in ANNEX["ambiguities"]:
        assert _in(a["celex"], a["quote"]), a["code"]
    for k in ("quote", "annex_quote"):
        assert _in("32025R1093", CC["legal_basis"][k])
    for q in CC["article_1"].values():
        assert _in("32025R1093", q)
    assert _in("32025R1093", CC["dates"]["published_quote"])
    assert _in("32025R1093", CC["dates"]["entry_into_force_quote"])
    assert _in("32025R1093", CC["sub_national"]["context_quote"])
    for cls in ("high", "low"):
        for r in CC[cls]:
            assert _in("32025R1093", r["name"]), r["name"]


def test_entry_counts_per_version():
    # counted in the texts: one entry per printed code (0102 21 , 0102 29 → 2; the 9403 row → 5; Chapters 47/48 → 2)
    counts = {v["id"]: len(v["entries"]) for v in ANNEX["versions"]}
    assert counts == {"original": 77, "amended_2025_2650": 76, "amended_2026_2102": 76,
                      "amended_2026_2102_from_2027_12_30": 93}
    later = [e for e in ANNEX["versions"][3]["entries"] if e.get("applies_from") == "2027-12-30"]
    assert len(later) == 18     # 17 printed with the 30.12.2027 clause + ex 1520 00 (ambiguous until then)


def test_country_counts_and_mapping():
    assert len(CC["high"]) == 4 and len(CC["low"]) == 140
    assert CC["unmapped"] == []
    codes = [r["iso2"] for c in ("high", "low") for r in CC[c]]
    assert len(codes) == len(set(codes))
    assert {r["iso2"] for r in CC["high"]} == {"BY", "KP", "MM", "RU"}
    assert CC["readings"][0]["printed"] == "Solomon Island" and CC["readings"][0]["read_as"] == "SB"


def test_scope_cases():
    assert R.scope("1801", date(2027, 1, 1))["in_scope"] is True
    assert R.scope("18010000", date(2027, 1, 1))["in_scope"] is True
    # ex 4107 (leather): an 'ex' entry before 18.9.2026, deleted by 2026/2102 from then on
    before = R.scope("410711", date(2026, 9, 17))
    assert before["in_scope"] is None and before["ex"] is True and before["description"].startswith("Leather of cattle")
    assert R.scope("410711", date(2026, 9, 18))["in_scope"] is False
    # ex 49 printed books: removed by 2025/2650 from 26.12.2025
    assert R.scope("4901", date(2025, 12, 25))["in_scope"] is None
    assert R.scope("4901", date(2025, 12, 26))["in_scope"] is False
    # added from 30.12.2027: 2101 11 00 coffee extracts
    assert R.scope("21011100", date(2027, 12, 29))["in_scope"] is False
    assert R.scope("21011100", date(2027, 12, 30))["in_scope"] is True
    # a 4-digit code against an 8-digit entry is not decided
    r = R.scope("1201", date(2026, 10, 1))
    assert r["in_scope"] is None and "narrower" in r["why"]
    assert R.scope("1201", date(2026, 9, 1))["in_scope"] is True
    # ex 1520 00: application clause outside the quote → undecided until 30.12.2027
    assert R.scope("15200000", date(2026, 10, 1))["in_scope"] is None
    assert R.scope("15200000", date(2027, 12, 30))["in_scope"] is None   # still an 'ex' entry
    assert R.scope("0901", date(2024, 1, 1))["in_scope"] is True
    with pytest.raises(ValueError):
        R.scope("0901", date(2023, 6, 28))


def test_country_risk():
    assert R.country_risk("RU")["risk"] == "high"
    assert R.country_risk("DE")["risk"] == "low"
    assert R.country_risk("EL")["risk"] == "low"          # EU code for Greece
    assert R.country_risk("BR")["risk"] == "standard"
    assert R.country_risk("ZZ") is None
    assert R.country_risk("BR", date(2025, 5, 25)) is None
