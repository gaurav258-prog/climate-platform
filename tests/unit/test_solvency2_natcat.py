"""Solvency II standard-formula NatCat — all five perils + Art. 120 aggregation (Del. Reg. 2015/35)."""
import json
import math

from services.governance.solvency2_natcat import natcat_scr, standard_formula_peril, subsidence_scr


def _pol(country, si):
    return {"country": country, "sum_insured_eur": si}


def test_gross_factors_per_peril():
    # SCR_r = gross · Q_r · SI_r for a single region; verifies each peril's prescribed gross factor
    si = 1_000_000_000
    assert standard_formula_peril([_pol("DE", si)], "windstorm")["per_region"][0]["scr_region_eur"] == round(1.20 * 0.0009 * si)
    assert standard_formula_peril([_pol("IT", si)], "earthquake")["per_region"][0]["scr_region_eur"] == round(1.00 * 0.0080 * si)
    assert standard_formula_peril([_pol("DE", si)], "flood")["per_region"][0]["scr_region_eur"] == round(1.10 * 0.0020 * si)
    assert standard_formula_peril([_pol("AT", si)], "hail")["per_region"][0]["scr_region_eur"] == round(1.20 * 0.0008 * si)


def test_earthquake_covers_southern_europe_that_windstorm_misses():
    # Greece has no windstorm factor but a high earthquake factor (1.85%)
    assert standard_formula_peril([_pol("GR", 1e9)], "windstorm")["available"] is False
    eq = standard_formula_peril([_pol("GR", 1e9)], "earthquake")
    assert eq["available"] and eq["per_region"][0]["region"] == "HE"
    assert eq["scr_eur"] == round(1.00 * 0.0185 * 1e9)


def test_san_marino_iso_maps_to_italy_region_for_earthquake():
    # ISO 'SM' is San Marino (part of the IT region), NOT Saint Martin here
    r = standard_formula_peril([_pol("SM", 1e9)], "earthquake")
    assert r["per_region"][0]["region"] == "IT"


def test_subsidence_is_france_only_fixed_factor():
    assert subsidence_scr([_pol("FR", 2e9)])["scr_eur"] == round(0.0005 * 2e9)   # 1,000,000
    assert subsidence_scr([_pol("DE", 2e9)])["available"] is False               # not France


def test_natcat_aggregates_five_perils_root_sum_of_squares():
    book = [_pol("DE", 1e9), _pol("IT", 1e9), _pol("FR", 1e9)]
    r = natcat_scr(book)
    by = r["scr_by_peril_eur"]
    expect = math.sqrt(sum(v * v for v in by.values()))
    assert abs(r["natcat_scr_eur"] - round(expect)) <= 1
    assert r["cross_peril_diversification_benefit_eur"] > 0     # independent perils diversify
    assert set(by) == {"windstorm", "earthquake", "flood", "hail", "subsidence"}


def test_natcat_available_false_when_no_eu_exposure():
    r = natcat_scr([_pol("US", 1e9), _pol("JP", 1e9)])
    assert r["available"] is False and all(v == 0 for v in r["scr_by_peril_eur"].values())


def test_all_annex_matrices_symmetric_unit_diagonal():
    # transcription guard across every peril's official correlation matrix
    ws = json.load(open("data/reference/solvency2_windstorm_annex_v.json"))
    nc = json.load(open("data/reference/solvency2_natcat_annexes.json"))
    mats = [("windstorm", ws)] + [(p, nc[p]) for p in ("earthquake", "flood", "hail")]
    for name, blk in mats:
        order, corr = blk["region_order"], blk["correlation"]
        idx = {r: i for i, r in enumerate(order)}
        assert set(corr) == set(order), f"{name}: rows != region_order"
        for r in order:
            assert len(corr[r]) == len(order) and corr[r][idx[r]] == 1.0, f"{name}: {r} diagonal"
            for s in order:
                assert corr[r][idx[s]] == corr[s][idx[r]], f"{name}: asymmetry {r},{s}"


def test_factors_and_regions_align():
    nc = json.load(open("data/reference/solvency2_natcat_annexes.json"))
    for p in ("earthquake", "flood", "hail"):
        assert set(nc[p]["regions"]) == set(nc[p]["region_order"])
        assert all(0 < nc[p]["regions"][r]["q"] < 0.1 for r in nc[p]["regions"])
