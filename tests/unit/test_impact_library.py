"""Impact-function library — archetype vulnerability + its composition into the damage function."""
from ml.scoring.damage_function import vulnerability_factor
from ml.scoring.impact_library import asset_type_factor, library_summary


def test_library_has_a_meaningful_catalogue():
    s = library_summary()
    assert s["n_asset_types"] >= 35
    for cat in ("residential", "commercial", "industrial", "power", "infrastructure", "agriculture"):
        assert cat in s["by_category"]


def test_archetype_factor_by_tier():
    # data centre is very-high heat sensitivity → the VH multiplier
    f, prov = asset_type_factor("com_data_centre", "heat")
    assert prov["applied"] and prov["tier"] == "VH" and f > 1.4
    # masonry dwelling is very-high seismic
    f2, prov2 = asset_type_factor("res_masonry", "seismic")
    assert prov2["tier"] == "VH" and f2 > 1.4
    # a bounded lower tier
    f3, _ = asset_type_factor("res_masonry", "wildfire")     # 'L'
    assert f3 < 1.0


def test_unknown_or_missing_is_neutral_not_fabricated():
    assert asset_type_factor(None, "flood")[0] == 1.0
    assert asset_type_factor("nonexistent", "flood")[0] == 1.0
    # a known archetype with no documented sensitivity for the hazard → neutral, with a reason
    f, prov = asset_type_factor("fin_equity_holding", "seismic")
    assert f == 1.0 and prov["applied"] is False


def test_chronic_peril_now_differentiated_via_archetype():
    # heat is a chronic peril the attribute model leaves neutral — the archetype restores differentiation
    f, prov = vulnerability_factor("heat", {"asset_type": "com_data_centre"})
    assert prov["applied"] is True and f > 1.0
    # without an asset type, chronic stays neutral (backward-compatible)
    f0, prov0 = vulnerability_factor("heat", {"construction_type": "masonry"})
    assert f0 == 1.0 and prov0["applied"] is False


def test_backward_compatible_structural_path():
    # unknown asset type → behaves like the attribute-only model (composition starts at 1.0)
    f, prov = vulnerability_factor("seismic", {"construction_type": "masonry", "year_built": 1960})
    assert prov["applied"] is True and f > 1.0     # masonry + old → more vulnerable, as before
    # archetype composes ON TOP when both are present, still bounded
    f2, _ = vulnerability_factor("seismic", {"asset_type": "res_masonry", "construction_type": "masonry"})
    assert 0.6 <= f2 <= 1.5
