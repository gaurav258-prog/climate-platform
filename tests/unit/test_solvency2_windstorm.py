"""Solvency II standard-formula windstorm CAT sub-module (Del. Reg. 2015/35, Art. 121 + Annex V)."""
import math

from services.governance.solvency2_windstorm import standard_formula_windstorm


def _pol(country, si):
    return {"country": country, "sum_insured_eur": si}


def test_single_region_is_gross_factor_times_q_times_si():
    # NL: Q=0.0018, SI=€1bn -> L=1.8m, SCR_r = 1.20*L = 2.16m; single region -> aggregate == SCR_r
    r = standard_formula_windstorm([_pol("NL", 1_000_000_000)])
    assert r["available"] and r["basis"] == "solvency_ii_standard_formula"
    assert r["scr_windstorm_eur"] == round(1.20 * 0.0018 * 1_000_000_000)   # 2,160,000
    assert r["per_region"][0]["windstorm_factor_q"] == 0.0018
    assert r["gross_of_reinsurance"] is True


def test_two_regions_apply_annex_v_correlation_and_give_diversification():
    # NL (SCR 2.16m) + DE (Q=0.0009 -> SCR 1.08m), CorrWS(NL,DE)=0.50
    r = standard_formula_windstorm([_pol("NL", 1_000_000_000), _pol("DE", 1_000_000_000)])
    scr_nl, scr_de = 1.20 * 0.0018e9, 1.20 * 0.0009e9
    expect = math.sqrt(scr_nl**2 + scr_de**2 + 2 * 0.50 * scr_nl * scr_de)
    assert abs(r["scr_windstorm_eur"] - round(expect)) <= 1
    assert r["undiversified_scr_eur"] == round(scr_nl + scr_de)
    assert r["regional_diversification_benefit_eur"] > 0   # correlation 0.5 < 1 -> a real benefit


def test_uncorrelated_regions_diversify_more_than_correlated():
    # ES-IS have CorrWS 0.00 (fully independent); NL-BE have 0.75 (highly correlated) -> less diversification
    indep = standard_formula_windstorm([_pol("ES", 1e9), _pol("IS", 1e9)])
    corr = standard_formula_windstorm([_pol("NL", 1e9), _pol("BE", 1e9)])
    # benefit as a share of the undiversified sum is larger when independent
    def share(x): return x["regional_diversification_benefit_eur"] / x["undiversified_scr_eur"]
    assert share(indep) > share(corr)


def test_non_annex_v_country_is_disclosed_not_dropped():
    r = standard_formula_windstorm([_pol("NL", 500_000_000), _pol("US", 900_000_000), _pol("JP", 100_000_000)])
    assert r["available"] and r["n_regions"] == 1
    assert r["other_regions_sum_insured_eur"] == 1_000_000_000   # US + JP tracked, not counted in the SF charge


def test_gb_and_overseas_map_to_regions():
    r = standard_formula_windstorm([_pol("GB", 1e9)])   # United Kingdom -> UK, Q=0.0017
    assert r["per_region"][0]["region"] == "UK"
    assert r["scr_windstorm_eur"] == round(1.20 * 0.0017 * 1e9)


def test_honest_when_no_windstorm_exposure():
    r = standard_formula_windstorm([_pol("US", 1e9), _pol("JP", 1e9)])
    assert r["available"] is False and "windstorm region" in r["reason"]
    assert r["other_regions_sum_insured_eur"] == 2_000_000_000


def test_annex_v_matrix_is_symmetric_with_unit_diagonal():
    # transcription guard: the official Annex V correlation matrix must be symmetric with 1.0 on the diagonal
    import json
    p = json.load(open("data/reference/solvency2_windstorm_annex_v.json"))
    order, corr = p["region_order"], p["correlation"]
    assert len(order) == 20 and all(len(corr[r]) == 20 for r in order)
    idx = {r: i for i, r in enumerate(order)}
    for r in order:
        assert corr[r][idx[r]] == 1.0
        for s in order:
            assert corr[r][idx[s]] == corr[s][idx[r]], f"asymmetry at {r},{s}"


def test_citation_present():
    r = standard_formula_windstorm([_pol("FR", 1e9)])
    assert "2015/35" in r["citation"] and "Annex V" in r["citation"]
    assert "Country-level" in r["approximation"]   # the disclosed simplification is surfaced
