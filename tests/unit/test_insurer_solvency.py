"""Solvency II S.27.01.01 natural-catastrophe block mapping — invariants."""
from services.governance.insurer_solvency import s2701_natcat


def _snap():
    return {
        "solvency_scr": {"available": True, "scr_basis": "internal_model_99_5_var", "natcat_scr_eur": 250_000_000,
                         "mean_annual_loss_eur": 37_000_000, "risk_load_eur": 213_000_000,
                         "scr_pct_of_sum_insured": 38.5, "note": "internal-model basis",
                         "standard_formula_natcat": {"available": True, "natcat_scr_eur": 12_000_000,
                             "scr_by_peril_eur": {"windstorm": 3_000_000, "earthquake": 11_000_000, "flood": 2_000_000,
                                                  "hail": 500_000, "subsidence": 500_000},
                             "citation": "Del. Reg. (EU) 2015/35, Art. 120-125", "perils": {}}},
        "reinsurance": {"net": {"net_aep_eur": {"rp_200": 200_000_000}}},
        "by_hazard": {
            "severe_convective": {"exposed_value_eur": 466_000_000, "n_exposed": 40},
            "subsidence": {"exposed_value_eur": 284_000_000, "n_exposed": 30},
            "flood": {"exposed_value_eur": 119_000_000, "n_exposed": 12},
            "drought": {"exposed_value_eur": 999_000_000, "n_exposed": 99},  # not a Solvency II nat-cat peril
        },
    }


def test_gross_and_net_scr():
    s = s2701_natcat(_snap())
    assert s["natcat_scr"]["gross_1_in_200_eur"] == 250_000_000
    assert s["natcat_scr"]["net_of_reinsurance_1_in_200_eur"] == 200_000_000


def test_only_natcat_perils_mapped():
    s = s2701_natcat(_snap())
    perils = {p["peril"] for p in s["perils"]}
    assert perils == {"Hail", "Subsidence", "Flood"}   # drought excluded (not a nat-cat peril line)


def test_standard_formula_natcat_surfaced_and_cited():
    s = s2701_natcat(_snap())
    sf = s["standard_formula_natcat"]
    assert sf and sf["available"] and sf["natcat_scr_eur"] == 12_000_000
    assert "2015/35" in sf["citation"]
    assert set(sf["scr_by_peril_eur"]) == {"windstorm", "earthquake", "flood", "hail", "subsidence"}


def test_out_of_scope_sub_modules_are_declared_and_the_template_is_s2701():
    s = s2701_natcat(_snap())
    assert s["template"] == "S.27.01.01" and s["declared"]["status"] == "declared"
    assert "man-made" in " ".join(s["declared"]["items"]).lower() and "90b" in s["declared"]["note"]


def test_a_filing_frozen_under_the_old_key_is_still_read():
    from services.governance.insurer_solvency import natcat_block
    assert natcat_block({"s2601": {"x": 1}}) == {"x": 1} and natcat_block({"s2701": {"y": 2}}) == {"y": 2}


def test_unavailable_when_no_scr():
    s = s2701_natcat({"solvency_scr": {"available": False, "reason": "no_scored_policies"}})
    assert s["available"] is False


def test_solo_scope_has_no_group_method_note():
    """Default (group_scope=False, the ordinary solo/whole-org case) — no group-solvency caveat needed."""
    s = s2701_natcat(_snap())
    assert s["group_method_note"] is None


def test_group_scope_discloses_it_is_not_a_group_solvency_position():
    """C3 (2026-09-23): a consolidated/group-scoped figure must explicitly say it's one Basic SCR sub-module
    on a weighted pool, not a Title III Method 1/2 group solvency position — never silently pass as one."""
    s = s2701_natcat(_snap(), group_scope=True)
    note = s["group_method_note"]
    assert note is not None
    assert note["status"] == "not_a_group_solvency_position"
    assert "Method 1" in note["note"] and "Method 2" in note["note"]
    assert "Title III" in note["regulation"]
