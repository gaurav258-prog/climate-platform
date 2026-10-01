"""Golden book for the Solvency II nat-cat standard formula (Del. Reg. (EU) 2015/35 Arts 90b, 119-126), worked by hand.

Table values used (Annex V, Annex X, Annex XXII, Annex XXVI — 02015R0035-20241114; asserted below as held):
  windstorm DE: Q = 0,07 %; zone 01 W = 0,9; zone 20 W = 1,4; Corr(01,20) = 0,25; highest W in DE = 2,9
  subsidence FR: zone 75 W = 0,3; zone 13 W = 2,5; Corr(75,13) = 1; factor 0,0005

1  exact zones   SI 100m in zone 01, 200m in zone 20
                 WSI = 0,0007·0,9·100m = 63 000 and 0,0007·1,4·200m = 196 000
                 L = √(63 000² + 196 000² + 2·0,25·63 000·196 000) = √48 559 000 000 = 220 361,07
                 gross, either scenario: 1,2·L = 264 433
2  treaty        quota share 30 %; excess of loss 50 000 xs 100 000 per event
   scenario A    event 1 = 0,8·L = 176 288,85: QS 52 886,66, retained 123 402,20, layer 23 402,20
                 event 2 = 0,4·L =  88 144,43: QS 26 443,33, retained  61 701,10, layer 0
                 recovered 102 732,18 → loss 264 433,28 − 102 732,18 = 161 701
   scenario B    event 1 = L: QS 66 108,32, layer 50 000 (limit used); event 2 = 0,2·L: QS 13 221,66
                 recovered 129 329,98 → loss 135 103 — A is the larger: 161 701
   reinstated    one reinstatement at 10 000 for the full limit: A pays 10 000 · 23 402,20/50 000 = 4 680 → 166 382;
                 B pays 10 000 → 145 103; A again
3  Art. 90b      100m in zone 01 and 100m without a postal code → all DE zones one group at W 2,9:
                 L = 0,0007·2,9·200m = 406 000; gross 487 200
4  subsidence    1bn in zone 75, 1bn in zone 13: WSI 150 000 and 1 250 000, Corr 1 → L = 1 400 000 (single scenario)
5  other regions US risk; premiums 5m in region 15 (NE US), 5m in region 18 (W US), 2m in region 1 (N Europe):
                 P = 12m; DIV over regions 5-18 = (5² + 5²) / 10² = 0,5 → L = 1,75·(0,5·0,5 + 0,5)·12m = 15 750 000
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from services.governance import solvency2_natcat_tables as T
from services.governance.solvency2_natcat import diversification, natcat_scr, peril_scr

D24, D27 = date(2025, 12, 31), date(2027, 6, 30)
TREATY = {"quota_share_pct": 30, "xol_attachment_eur": 100_000, "xol_limit_eur": 50_000}


def _ws(pols, treaty=None, **kw):
    return peril_scr(pols, "windstorm", v=T.version(D24), treaty=treaty, **kw)


def test_the_table_values_the_golden_book_uses_are_held():
    v = T.version(D24)
    ws, de = T.peril_table(v, "windstorm"), T.zonal(v, "windstorm", "DE")
    assert ws["regions"]["DE"]["q"] == 0.0007
    assert (de["zones"]["1"]["w"], de["zones"]["20"]["w"], de["correlation"]["1"]["20"]) == (0.9, 1.4, 0.25)
    assert max(z["w"] for z in de["zones"].values()) == 2.9
    fr = T.zonal(v, "subsidence", "FR")
    assert (fr["zones"]["75"]["w"], fr["zones"]["13"]["w"], fr["correlation"]["75"]["13"]) == (0.3, 2.5, 1.0)


def test_exact_zones_give_the_specified_loss_and_either_scenario_gross():
    r = _ws([{"country": "DE", "postal_code": "01067", "sum_insured_eur": 100e6},
             {"country": "DE", "postal_code": "20095", "sum_insured_eur": 200e6}])["regions"][0]
    assert (r["method"], r["specified_gross_loss_eur"], r["before_eur"], r["after_eur"]) == ("exact_zonal", 220361, 264433, 264433)
    assert r["scenario"] == "A"                                     # a tie keeps A


def test_the_larger_scenario_after_the_treaty_is_the_charge():
    pols = [{"country": "DE", "postal_code": "01067", "sum_insured_eur": 100e6},
            {"country": "DE", "postal_code": "20095", "sum_insured_eur": 200e6}]
    r = _ws(pols, TREATY)["regions"][0]
    assert (r["scenario"], r["after_eur"], r["mitigation_eur"], r["reinstatement_eur"]) == ("A", 161701, 102732, 0)
    r = _ws(pols, {**TREATY, "xol_reinstatements": 1, "xol_reinstatement_premium_eur": 10_000})["regions"][0]
    assert (r["scenario"], r["after_eur"], r["reinstatement_eur"]) == ("A", 166382, 4680)
    # reinstatements stated without their premium: none assumed (declared reading) — same as not stated
    assert _ws(pols, {**TREATY, "xol_reinstatements": 1})["regions"][0]["after_eur"] == 161701


def test_a_risk_without_a_zone_groups_the_region_under_art_90b():
    r = _ws([{"country": "DE", "postal_code": "01067", "sum_insured_eur": 100e6},
             {"country": "DE", "sum_insured_eur": 100e6}])["regions"][0]
    assert (r["method"], r["specified_gross_loss_eur"], r["before_eur"]) == ("grouped_art90b", 406000, 487200)
    assert "50 %" in r["method_reason"]


def test_zone_labels_that_cannot_be_matched_are_always_grouped():
    v = T.version(D24)
    r = peril_scr([{"country": "SI", "postal_code": "5000", "sum_insured_eur": 1e8}], "earthquake", v=v)["regions"][0]
    assert r["method"] == "grouped_art90b" and "labels" in r["method_reason"]


def test_subsidence_before_2027_is_france_residential_on_the_zones():
    v = T.version(D24)
    r = peril_scr([{"country": "FR", "postal_code": "75001", "sum_insured_eur": 1e9},
                   {"country": "FR", "postal_code": "13001", "sum_insured_eur": 1e9},
                   {"country": "FR", "postal_code": "13002", "sum_insured_eur": 5e8, "residential": False},
                   {"country": "BE", "postal_code": "1000", "sum_insured_eur": 1e9}], "subsidence", v=v)
    assert [(x["region"], x["method"], x["before_eur"]) for x in r["regions"]] == [("FR", "exact_zonal", 1_400_000)]
    assert r["other_regions"] is None and r["residential_not_stated"] == 2


def test_other_regions_are_charged_on_attested_premiums_and_never_on_zero():
    pols = [{"country": "US", "sum_insured_eur": 1e9}]
    missing = _ws(pols)
    assert missing["other_regions"]["status"] == "missing_input" and not missing["complete"]
    got = _ws(pols, other_inputs={"windstorm": {"by_region": {15: 5e6, 18: 5e6, 1: 2e6}}})
    assert (got["other_regions"]["div"], got["other_regions"]["before_eur"], got["complete"]) == (0.5, 15_750_000, True)
    assert diversification({1: 2e6, 2: 3e6}) == 1.0                  # nothing in regions 5-18: no diversification
    # stated premiums are charged even where the uploaded book holds none of those risks (the charge is on premiums)
    only_p = _ws([{"country": "DE", "sum_insured_eur": 1e6}], other_inputs={"windstorm": {"by_region": {15: 5e6, 18: 5e6, 1: 2e6}}})
    assert only_p["other_regions"]["exposure_eur"] == 0 and only_p["other_regions"]["before_eur"] == 15_750_000


def test_a_region_and_other_regions_combine_independently():
    pols = [{"country": "DE", "sum_insured_eur": 100e6}, {"country": "US", "sum_insured_eur": 1e9}]
    r = _ws(pols, other_inputs={"windstorm": {"by_region": {15: 5e6, 18: 5e6, 1: 2e6}}})
    assert r["before_eur"] == round((243_600 ** 2 + 15_750_000 ** 2) ** 0.5)     # DE grouped: 1,2·0,0007·2,9·100m


def test_the_united_kingdom_is_charged_by_region_unless_the_literal_reading_is_chosen():
    pols = [{"country": "UK", "sum_insured_eur": 1e9}]              # the EU's code: read as GB
    assert _ws(pols)["other_regions"] is None and _ws(pols)["regions"][0]["region"] == "UK"
    lit = _ws(pols, uk_reading="region_and_premium")
    assert lit["other_regions"]["exposure_eur"] == 1_000_000_000


def test_a_greek_risk_in_the_eus_own_code_carries_its_earthquake_charge():
    r = peril_scr([{"country": "EL", "sum_insured_eur": 1e9}], "earthquake", v=T.version(D24))
    assert r["regions"][0]["region"] == "HE" and r["regions"][0]["before_eur"] > 0          # E38


def test_only_an_attested_treaty_mitigates():
    pols = [{"country": "DE", "sum_insured_eur": 1e9}]
    ill = natcat_scr(pols, ref_date=D24, treaty=TREATY, treaty_basis="not_attested")
    assert ill["treaty_basis"] == "none" and ill["natcat_scr_eur"] == ill["natcat_scr_before_mitigation_eur"]
    att = natcat_scr(pols, ref_date=D24, treaty=TREATY, treaty_basis="attested")
    assert att["natcat_scr_eur"] < att["natcat_scr_before_mitigation_eur"]


def test_perils_combine_as_independent_and_the_version_follows_the_date():
    pols = [{"country": "DE", "sum_insured_eur": 1e9, "motor_sum_insured_eur": 1e6}]
    r = natcat_scr(pols, ref_date=D24)
    by = {p: x["before_eur"] for p, x in r["perils"].items() if x["available"]}
    assert r["natcat_scr_before_mitigation_eur"] == round(sum(b * b for b in by.values()) ** 0.5)
    assert r["version"] == "da_2015_35_as_2019_981" and natcat_scr(pols, ref_date=D27)["version"] == "da_2015_35_as_2026_269"
    motor = [{"country": "DE", "sum_insured_eur": 0, "motor_sum_insured_eur": 1e6}]
    h24 = peril_scr(motor, "hail", v=T.version(D24))["regions"][0]["exposure_eur"]
    h27 = peril_scr(motor, "hail", v=T.version(D27))["regions"][0]["exposure_eur"]
    assert (h24, h27) == (5_000_000, 10_000_000)                  # Art. 124(7): 5 → 10 by 2026/269


def test_from_2027_subsidence_is_regional_france_and_belgium():
    v = T.version(D27)
    r = peril_scr([{"country": "BE", "postal_code": "1000", "sum_insured_eur": 1e9},
                   {"country": "US", "sum_insured_eur": 1e9}], "subsidence", v=v)
    assert [x["region"] for x in r["regions"]] == ["BE"] and r["other_regions"]["status"] == "not_calculated"


@pytest.mark.parametrize("when", [D24, D27])
def test_every_zone_table_and_postal_map_is_whole(when):
    """Each zoned region: weights and correlations over the same zones, symmetric, unit diagonal; a labels_verified
    flag; every Annex IX map entry names a zone of the region."""
    v = T.version(when)
    zf = json.load(open(f"data/reference/{v['files']['zonal']}"))
    ix = T.annex_ix(v)
    for peril in ("windstorm", "earthquake", "flood", "hail", "subsidence"):
        for region, t in zf[peril].items():
            zs = set(t["zones"])
            assert zs == set(t["correlation"]) and "labels_verified" in t, (peril, region)
            assert all(t["correlation"][i][i] == 1.0 and t["correlation"][i][j] == t["correlation"][j][i]
                       for i in zs for j in zs), (peril, region)
            spec = (ix.get(peril) or {}).get(region) or {}
            assert set(spec.get("map", {}).values()) <= zs or spec.get("basis") in ("admin_unit", "not_postal"), (peril, region)
