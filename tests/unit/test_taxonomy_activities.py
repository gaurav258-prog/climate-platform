"""The EU Taxonomy activity reference (captured from the Delegated Acts) and the classifier that reads it (E30):
a NACE code decides the activity only where every activity listing it is the same activity."""
import collections
import re

from ml.regulatory.eu_taxonomy_classifier import classify_taxonomy
from services.reference import taxonomy_activities as T


def test_the_reference_is_complete_and_consistent():
    acts = T.activities()
    by_obj = collections.Counter(a["objective"] for a in acts)
    # 2021/2139 Annex I 88 + 2022/1214 6 + 2023/2485 7; Annex II 95 + 6 + 5; 2023/2486 Annexes I-IV 6 + 21 + 6 + 2
    assert by_obj == {"ccm": 101, "cca": 106, "wtr": 6, "ce": 21, "ppc": 6, "bio": 2}
    codes = [a["code"] for a in acts]
    assert len(codes) == len(set(codes))
    assert all(re.fullmatch(r"(CCM|CCA|WTR|CE|PPC|BIO) \d+(\.\d+)?", c) for c in codes)
    assert all(a["code"].split()[0].lower() == a["objective"] for a in acts)
    assert all(a["nace_quote"] for a in acts)                      # every activity carries its verbatim NACE sentence
    assert all(a["category"] in (None, "transitional", "enabling") for a in acts)
    assert all(a["category_quote"] for a in acts if a["category"])


def test_a_nace_code_decides_the_activity_only_when_it_is_one_activity():
    r = classify_taxonomy("68.20")
    assert r["status"] == "eligible" and r["activity_ref"].startswith("CCM 7.7 / CCA 7.7")
    # electricity generation: solar, wind, gas … — several activities (and coal none): not decided by the NACE code
    r = classify_taxonomy("35.11")
    assert r["status"] == "not_determined" and r["activity_ref"] is None
    assert any(c.startswith("CCM 4.1 ") for c in r["reasoning"]["candidate_activities"])
    r = classify_taxonomy("64.19")
    assert r["status"] == "not_eligible" and "no Taxonomy activity" in r["reasoning"]["nace_basis"]


def test_the_building_epc_test_applies_only_to_buildings():
    assert classify_taxonomy("68.20", epc_rating="A")["reasoning"]["substantial_contribution_verified"] is True
    assert classify_taxonomy("35.11", epc_rating="A")["reasoning"]["substantial_contribution_verified"] is False


def test_the_phase_in_reads_to_activity_codes():
    """Art. 10(6)/(7) of 2021/2178 (added by 2023/2486): every activity of the four new objectives plus the cited
    sections of 2021/2139 — Annex I is mitigation (its Article 1), Annex II adaptation (Article 2)."""
    import services.regspec as R
    ph = R.load("bank_taxonomy", "da_2021_2178_as_amended_2023_2486")["phase_in"][0]
    codes = T.eligibility_only(ph)
    assert len(codes) == 6 + 21 + 6 + 2 + 7 + 5
    assert {"CCM 3.18", "CCM 3.21", "CCM 6.18", "CCM 6.20", "CCA 5.13", "CCA 8.4", "CCA 9.3", "CCA 14.1", "CCA 14.2"} <= codes
    assert "CCM 7.7" not in codes and "CCA 7.7" not in codes
    # the cited sections are exactly those 2023/2485 added — nothing else of the climate acts is caught
    assert {c for c in codes if c[:3] in ("CCM", "CCA")} == {a["code"] for a in T.activities() if a["introduced_by"] == "32023R2485"}


def test_a_cited_section_that_does_not_exist_is_a_declared_finding():
    """The Article cites Section 7.8 of Annex II to 2021/2139, which no act contains: it narrows nothing, and the finding
    is declared in the reference (a new unmatched citation without one raises)."""
    import pytest

    import services.regspec as R
    ph = R.load("bank_taxonomy", "da_2021_2178_as_amended_2023_2486")["phase_in"][0]
    assert [u["cited"] for u in T.unmatched(ph)] == ["Section 7.8 of Annex II to Delegated Regulation (EU) 2021/2139"]
    assert T.by_code("CCA 7.8") is None
    bad = {"eligibility_only": {"activities": {"Delegated Regulation (EU) 2021/2139 Annex II": ["99.9"]}}}
    with pytest.raises(ValueError, match="no declared finding"):
        T.unmatched(bad)


def test_both_undertakings_phase_in_the_same_activities():
    """Non-financial (Art. 10(6), disclosures in 2024) and financial undertakings (Art. 10(7), 2024-2025) phase in the
    same activities; only the window differs."""
    import services.regspec as R
    nf = R.load("nonfin_taxonomy", "da_2021_2178_as_amended_2023_2486")["phase_in"][0]
    bk = R.load("bank_taxonomy", "da_2021_2178_as_amended_2023_2486")["phase_in"][0]
    assert T.eligibility_only(nf) == T.eligibility_only(bk)
    assert (nf["disclosures"], bk["disclosures"]) == ({"from": "2024-01-01", "until": "2024-12-31"},
                                                     {"from": "2024-01-01", "until": "2025-12-31"})


def test_codes_of_a_stated_activity():
    assert T.codes_of("CCM 7.7 / CCA 7.7 — Acquisition and ownership of buildings") == ["CCM 7.7", "CCA 7.7"]
    assert T.codes_of("Real estate") == [] and T.codes_of(None) == []


def test_a_phase_in_part_no_engine_reads_fails_validation():
    """E32: the bank spec quoted an activity-level phase-in the engine did not apply. Every part must have a reader."""
    import copy

    import services.regspec as R
    spec = copy.deepcopy(R.load("bank_taxonomy", "da_2021_2178_as_amended_2023_2486"))
    assert R.validate(spec) == []
    spec["phase_in"][0]["eligibility_only"]["sectors"] = ["C29"]
    assert any("no engine reads" in e for e in R.validate(spec))
