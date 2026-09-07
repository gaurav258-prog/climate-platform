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


def test_motor_component_flood_hail_only():
    # Art. 123(7): flood SI = property + 1.5·motor; Art. 124(7): hail SI = property + 5·motor; windstorm/EQ: none
    pol = {"country": "DE", "sum_insured_eur": 1_000_000_000, "motor_sum_insured_eur": 1_000_000_000}
    fl = standard_formula_peril([pol], "flood")
    assert fl["per_region"][0]["scr_region_eur"] == round(1.10 * 0.0020 * (1e9 + 1.5 * 1e9))  # motor ×1.5
    assert fl["motor_component_eur"] == round(1.5 * 1e9)
    ha = standard_formula_peril([pol], "hail")
    assert ha["motor_component_eur"] == round(5.0 * 1e9)                                        # motor ×5
    ws = standard_formula_peril([pol], "windstorm")
    assert ws["per_region"][0]["scr_region_eur"] == round(1.20 * 0.0009 * 1e9)                  # property only, no motor
    assert ws["motor_component_eur"] is None


def test_property_book_has_zero_motor():
    r = standard_formula_peril([{"country": "DE", "sum_insured_eur": 1e9}], "flood")
    assert r["motor_component_eur"] == 0   # no motor_sum_insured on a property Statement of Values


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


def _hr(zone, si):
    p = {"country": "HR", "sum_insured_eur": si}
    if zone is not None:
        p["cresta_zone"] = zone
    return p


def test_exact_zonal_uses_weights_and_correlation_and_beats_country_level():
    # Croatia earthquake tables are loaded (CR); zone-tagged policies use the exact zonal calc
    zoned = standard_formula_peril([_hr(21, 1e9), _hr(8, 1e9)], "earthquake")
    country = standard_formula_peril([_hr(None, 1e9), _hr(None, 1e9)], "earthquake")
    assert zoned["per_region"][0]["method"] == "exact_zonal" and zoned["n_exact_zonal_regions"] == 1
    assert country["per_region"][0]["method"] == "country_level"
    # exact zonal takes within-country diversification credit -> strictly lower than the perfect-correlation approx
    assert zoned["scr_eur"] < country["scr_eur"]


def test_zonal_falls_back_when_a_policy_has_no_zone():
    # if ANY policy in the region lacks a cresta_zone, that region uses the country-level approximation (honest)
    r = standard_formula_peril([_hr(21, 1e9), _hr(None, 1e9)], "earthquake")
    assert r["per_region"][0]["method"] == "country_level"


def test_zonal_falls_back_on_unknown_zone():
    # a cited zone the table doesn't know -> fall back, never fabricate
    r = standard_formula_peril([_hr(999, 1e9)], "earthquake")
    assert r["per_region"][0]["method"] == "country_level"


def test_zonal_only_where_tables_loaded():
    # Italy earthquake has no zonal table yet -> country-level even with a zone tag
    r = standard_formula_peril([{"country": "IT", "sum_insured_eur": 1e9, "cresta_zone": 3}], "earthquake")
    assert r["per_region"][0]["method"] == "country_level"


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


def _de(zone, si):
    p = {"country": "DE", "sum_insured_eur": si}
    if zone is not None:
        p["cresta_zone"] = zone
    return p


def test_germany_exact_zonal_all_four_perils_matches_formula():
    # Germany's zones are 2-digit postcodes (non-contiguous ids, id-keyed). Check the engine reproduces the exact
    # Art.121-124(5) formula from the reference tables:  SCR = gross · Q_DE · sqrt(ΣΣ Corr(i,j)·W_i·SI_i·W_j·SI_j).
    # (Not a directional check: real zone weights run up to 5.0, so exact can sit above OR below the W=1 approx.)
    zonal = json.load(open("data/reference/solvency2_zonal.json"))
    ws = json.load(open("data/reference/solvency2_windstorm_annex_v.json"))
    nc = json.load(open("data/reference/solvency2_natcat_annexes.json"))
    gross = {"windstorm": 1.20, "earthquake": 1.00, "flood": 1.10, "hail": 1.20}
    book = {20: 1e9, 80: 1e9, 99: 5e8}   # Hamburg-ish, Munich-ish, Thuringia-ish postcodes
    for peril in ("windstorm", "earthquake", "flood", "hail"):
        q = (ws if peril == "windstorm" else nc[peril])["regions"]["DE"]["q"]
        t = zonal[peril]["DE"]
        wsi = {z: t["zones"][str(z)]["w"] * si for z, si in book.items()}
        var = sum(t["correlation"][str(i)][str(j)] * wsi[i] * wsi[j] for i in wsi for j in wsi)
        expected = gross[peril] * q * math.sqrt(var)
        z = standard_formula_peril([_de(k, v) for k, v in book.items()], peril)
        assert z["per_region"][0]["method"] == "exact_zonal", peril
        assert abs(z["scr_eur"] - round(expected)) <= 1, (peril, z["scr_eur"], expected)


def test_germany_nonexistent_postcode_falls_back():
    # 05 / 11 / 43 / 62 are not German postcodes and are absent from Annex IX -> honest fall-back, never fabricated
    r = standard_formula_peril([_de(5, 1e9)], "windstorm")
    assert r["per_region"][0]["method"] == "country_level"
