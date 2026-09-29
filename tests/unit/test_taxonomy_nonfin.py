"""Golden book for the non-financial Taxonomy templates (Annex II of Del. Reg. 2021/2178) of a building owner — worked
by hand from the 7.7 criteria (data/reference/taxonomy/criteria/ccm_7_7.json) and checked in three versions.

  P1 office, built 2005, EPC A, 150 kW, adaptation plan, safeguards compliant, gross rent 100      → aligned
  P2 retail, built 2005, EPC C, not in the top 15 %, plan, safeguards compliant, gross rent 50     → eligible, not aligned
  P3 logistics, built 2010, EPC B, top-15 % evidence not stated, gross rent 30                     → alignment not known
  P4 a building the classifier finds not eligible, gross rent 20                                   → non-eligible (B)
  P5 office, built 2000, EPC A, 400 kW with energy monitoring, plan, compliant; no gross rent, NOI 40 → aligned (proxy)
Turnover 240; eligible 220; aligned (A.1) 140 = 58.33 %; A.2 50 = 20.83 %; not known 30; B 20 = 8.33 %.
"""
from datetime import date

import pytest

import services.regspec as R
from services.governance import taxonomy_nonfin as N

ACT = "CCM 7.7 / CCA 7.7 — Acquisition and ownership of buildings"
EL = {"taxonomy_status": "eligible", "taxonomy_activity_ref": ACT, "hazards": [{"hazard": "flood"}]}
BOOK = [
    {**EL, "property_type": "office", "year_built": 2005, "epc_rating": "A", "heating_rated_output_kw": 150,
     "adaptation_plan_in_place": True, "minimum_safeguards_status": "compliant", "annual_gross_rental_revenue_eur": 100},
    {**EL, "property_type": "retail", "year_built": 2005, "epc_rating": "C", "ped_top15_evidence": False,
     "adaptation_plan_in_place": True, "minimum_safeguards_status": "compliant", "annual_gross_rental_revenue_eur": 50},
    {**EL, "property_type": "logistics", "year_built": 2010, "epc_rating": "B", "annual_gross_rental_revenue_eur": 30},
    {"taxonomy_status": "not_eligible", "property_type": "office", "annual_gross_rental_revenue_eur": 20},
    {**EL, "property_type": "office", "year_built": 2000, "epc_rating": "A", "heating_rated_output_kw": 400,
     "energy_performance_monitoring": True, "adaptation_plan_in_place": True, "minimum_safeguards_status": "compliant",
     "annual_noi_eur": 40},
]
PE = date(2025, 12, 31)


def _build(version):
    spec = R.load("nonfin_taxonomy", version)
    return spec, N.build(spec, BOOK, PE)


def test_2023_template_1_splits_aligned_eligible_and_non_eligible():
    spec, out = _build("da_2021_2178_as_amended_2023_2486")
    t1 = out["T1"]["turnover"]
    assert (t1["r4"]["3"], t1["r4"]["4"]) == (140, pytest.approx(58.33))          # A.1
    assert (t1["r8"]["3"], t1["r8"]["4"]) == (50, pytest.approx(20.83))           # A.2
    assert (t1["r9"]["3"], t1["r10"]["3"], t1["r11"]["3"]) == (220, 20, 240)       # A (A.1 + A.2 + not known), B, total
    row = next(v for k, v in t1.items() if k.startswith("r1:"))                   # the aligned activity, in A.1
    assert (row["2"], row["5"], row["6"], row["7"]) == (ACT.split(" — ")[0], "Y", "N", "N/EL")
    assert (row["12"], row["17"]) == ("Y", "Y")
    assert out["counts"]["alignment_unknown"] == 1 and out["counts"]["noi_proxy"] == 1
    assert sorted(k for k in t1 if ":" in k) == ["r1:0", "r7:0"]                 # one activity per group, listed once
    assert out["T2"]["capex"] == {"_input": "ledger"}                               # CapEx: the undertaking's ledger


def test_2023_per_objective_table():
    _, out = _build("da_2021_2178_as_amended_2023_2486")
    t1a = out["T1a"]["turnover"]
    assert (t1a["CCM"]["c1"], t1a["CCM"]["c2"]) == (pytest.approx(58.33), pytest.approx(91.67))
    assert (t1a["CCA"]["c1"], t1a["CCA"]["c2"]) == (0, pytest.approx(91.67))      # eligible under both objectives


def test_2026_summary_and_activity_breakdown():
    _, out = _build("da_2021_2178_as_amended_2026_73")
    r = out["T1"]["all"]["r1"]
    assert (r["2"], r["3"], r["4"], r["5"], r["6"]) == (240, pytest.approx(91.67), 140, pytest.approx(58.33), pytest.approx(58.33))
    capex = out["T1"]["all"]["r2"]                                                  # CapEx row: the undertaking's ledger
    assert capex["1"] == "CapEx" and capex["2"] == {"_input": "ledger"}
    t2 = out["T2"]["turnover"]
    act = next(v for k, v in t2.items() if ":" in k)
    assert act["4"] == 140 and act["5"] == pytest.approx(58.33)


def test_2021_templates_show_percentages_not_codes():
    _, out = _build("da_2021_2178")
    row = next(v for k, v in out["T_turnover"]["turnover"].items() if ":" in k and v.get("_activity"))
    assert isinstance(next(v for c, v in row.items() if c not in ("_activity", "_codes") and isinstance(v, float)), float)


def test_every_building_sits_in_exactly_one_place_and_aligned_never_exceeds_eligible():
    """An invariant of the engine: aligned + not aligned + not known = eligible; eligible + non-eligible = turnover."""
    from services.governance.taxonomy_nonfin import summary
    sm = summary(BOOK)
    assert sm["aligned"] + sm["not_aligned"] + sm["unknown"] == sm["eligible"]
    assert sm["eligible"] + sm["non_eligible"] == sm["turnover"] and sm["aligned"] <= sm["eligible"]


def test_previous_year_is_blank_without_a_previous_filing():
    _, out = _build("da_2021_2178_as_amended_2026_73")
    r = out["T1"]["all"]["r1"]
    assert r["15"] is None and r["16"] is None                                     # never 0 for 'not known'


def test_the_phase_in_leaves_a_new_activity_undecided():
    """Art. 10(6): for disclosures made in 2024 an activity 2023/2485 added (CCA 14.2) is reported for eligibility only
    — eligible, in neither A.1 nor A.2, with the reason; the 7.7 buildings are unaffected."""
    flood = {"taxonomy_status": "eligible", "annual_gross_rental_revenue_eur": 10,
             "taxonomy_activity_ref": "CCA 14.2 — Flood risk prevention and protection infrastructure"}
    spec = R.load("nonfin_taxonomy", "da_2021_2178_as_amended_2023_2486")
    out = N.build(spec, BOOK + [flood], date(2023, 12, 31), disclosure_date=date(2024, 4, 30))
    c = out["counts"]
    assert c["phase_in"]["ref"].startswith("Article 10(6)")
    assert (c["eligible"], c["alignment_unknown_turnover"]) == (230, 40)             # 30 (P3) + 10 (phased)
    assert (c["phased"], c["phased_turnover"]) == (1, 10)
    assert not any(r.startswith("eligibility only") for r, _ in c["unknown_reasons"])   # not a missing fact
    later = N.build(spec, BOOK + [flood], date(2024, 12, 31), disclosure_date=date(2025, 4, 30))
    assert later["counts"]["phase_in"] is None
