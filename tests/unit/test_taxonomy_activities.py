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
