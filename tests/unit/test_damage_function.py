"""The core hazard→€ damage function: continuous, within-band, vulnerability-differentiated, honest.

Pins the properties that make it defensible — no bucket cliffs, never inflates past the disclosed
band, ordering follows published vulnerability, chronic perils stay neutral, and a missing attribute
is neutral-and-flagged rather than guessed.
"""
from ml.scoring import damage_function as df


def test_haircut_is_continuous_no_cliff():
    # The old 4-bucket table jumped 5%→15% at score 50. The curve must not.
    a = df.collateral_haircut_pct(49.9, "M")
    b = df.collateral_haircut_pct(50.1, "H")
    assert abs(a - b) < 1.0


def test_haircut_monotone_in_score():
    vals = [df.collateral_haircut_pct(s, None) for s in range(0, 101, 5)]
    assert all(vals[i] <= vals[i + 1] + 1e-9 for i in range(len(vals) - 1))


def test_bucket_only_reproduces_disclosed_schedule():
    # A legacy bucket-only caller (no score/attrs) reproduces the disclosed value exactly.
    assert df.collateral_haircut_pct(None, "H") == df.RECOMMENDED_DISCOUNT_PCT["H"]
    assert df.collateral_haircut_pct(None, "VH") == df.RECOMMENDED_DISCOUNT_PCT["VH"]
    assert df.collateral_haircut_pct(0, "L") == 0.0


def test_within_band_never_inflates():
    high_vuln = {"construction_type": "unreinforced masonry", "year_built": 1955, "number_of_stories": 1}
    # even a maximally-vulnerable asset at score 100 stays within the peril's disclosed VH cap
    assert df.collateral_haircut_pct(100, "VH", hazard="seismic", attrs=high_vuln) <= df.RECOMMENDED_DISCOUNT_PCT["VH"]
    assert (df.collateral_haircut_pct(100, "VH", hazard="seismic", severity_model="peril_specific", attrs=high_vuln)
            <= df.PERIL_DISCOUNT_PCT["seismic"]["VH"])


def test_vulnerability_ordering_seismic():
    urm = {"construction_type": "masonry", "year_built": 1960}
    rc = {"construction_type": "reinforced concrete", "year_built": 2018}
    assert df.vulnerability_factor("seismic", urm)[0] > df.vulnerability_factor("seismic", rc)[0]
    assert (df.collateral_haircut_pct(70, "H", hazard="seismic", attrs=urm)
            > df.collateral_haircut_pct(70, "H", hazard="seismic", attrs=rc))


def test_vulnerability_ordering_fire_and_age():
    assert (df.vulnerability_factor("wildfire", {"construction_type": "timber frame"})[0]
            > df.vulnerability_factor("wildfire", {"construction_type": "concrete"})[0])
    # older stock is more wind-vulnerable
    assert (df.vulnerability_factor("storm", {"year_built": 1970})[0]
            > df.vulnerability_factor("storm", {"year_built": 2020})[0])


def test_chronic_perils_are_vulnerability_neutral():
    attrs = {"construction_type": "masonry", "year_built": 1950}
    for hz in ("heat_chronic", "heat_acute", "drought", "pollution", "frost", "soil_water"):
        f, prov = df.vulnerability_factor(hz, attrs)
        assert f == 1.0
        assert prov["applied"] is False


def test_missing_attributes_are_neutral_and_flagged():
    f, prov = df.vulnerability_factor("seismic", None)
    assert f == 1.0
    assert prov["complete"] is False
    f2, _ = df.vulnerability_factor("flood", {"construction_type": None, "year_built": None})
    assert f2 == 1.0


def test_factor_is_bounded():
    extreme = {"construction_type": "unreinforced masonry", "year_built": 1900, "number_of_stories": 1}
    for hz in ("seismic", "wildfire", "storm", "flood"):
        f, _ = df.vulnerability_factor(hz, extreme)
        assert df._VF_MIN <= f <= df._VF_MAX


def test_mdr_monotone_bounded_and_vulnerability_raises_it():
    prev = -1.0
    for s in range(0, 101, 5):
        m = df.mean_damage_ratio(s)
        assert 0.0 <= m <= 1.0 and m >= prev
        prev = m
    assert (df.mean_damage_ratio(60, "wildfire", {"construction_type": "timber"})
            > df.mean_damage_ratio(60, "wildfire", None))


def test_iso_construction_classes_map_to_families():
    # insurance books carry ISO/ISO-CGL construction classes, not free-text materials.
    assert df._construction_class("frame") == "wood"
    assert df._construction_class("joisted_masonry") == "masonry"
    assert df._construction_class("masonry_non_combustible") == "masonry"  # masonry wins over combustible
    assert df._construction_class("fire_resistive") == "concrete"
    assert df._construction_class("non_combustible") == "steel"
    # a fire-resistive building is less wildfire-vulnerable than a frame one at the same score.
    assert (df.vulnerability_factor("wildfire", {"construction_type": "frame"})[0]
            > df.vulnerability_factor("wildfire", {"construction_type": "fire_resistive"})[0])

