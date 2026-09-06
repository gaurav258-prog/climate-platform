"""Solvency II S.26.01.01 NatCat SCR mapping — invariants."""
from services.governance.insurer_solvency import s2601_natcat


def _snap():
    return {
        "solvency_scr": {"available": True, "scr_basis": "internal_model_99_5_var", "natcat_scr_eur": 250_000_000,
                         "mean_annual_loss_eur": 37_000_000, "risk_load_eur": 213_000_000,
                         "scr_pct_of_sum_insured": 38.5, "note": "internal-model basis"},
        "reinsurance": {"net": {"net_aep_eur": {"rp_200": 200_000_000}}},
        "by_hazard": {
            "severe_convective": {"exposed_value_eur": 466_000_000, "n_exposed": 40},
            "subsidence": {"exposed_value_eur": 284_000_000, "n_exposed": 30},
            "flood": {"exposed_value_eur": 119_000_000, "n_exposed": 12},
            "drought": {"exposed_value_eur": 999_000_000, "n_exposed": 99},  # not a S.26.01 nat-cat peril
        },
    }


def test_gross_and_net_scr():
    s = s2601_natcat(_snap())
    assert s["natcat_scr"]["gross_1_in_200_eur"] == 250_000_000
    assert s["natcat_scr"]["net_of_reinsurance_1_in_200_eur"] == 200_000_000


def test_only_natcat_perils_mapped():
    s = s2601_natcat(_snap())
    perils = {p["peril"] for p in s["perils"]}
    assert perils == {"Hail", "Subsidence", "Flood"}   # drought excluded (not a nat-cat peril line)


def test_standard_formula_cells_declared_not_fabricated():
    s = s2601_natcat(_snap())
    assert s["declared"]["status"] == "declared_external"
    assert any("standard-formula" in it.lower() for it in s["declared"]["items"])


def test_unavailable_when_no_scr():
    s = s2601_natcat({"solvency_scr": {"available": False, "reason": "no_scored_policies"}})
    assert s["available"] is False
