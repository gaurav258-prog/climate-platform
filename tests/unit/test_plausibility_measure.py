"""The exposure measure is configuration-driven: a sector's profile names the column, the label and the prior —
never a sector branch in code. These tests are pure: no session, no DB."""
import pytest

from services.supervision.exposure_prior import POPULATION, PRIOR_LABEL, SCORED_LAND, weighted_rows
from services.supervision.plausibility import DEFAULT_FIELD, exposure_measure, share_of


def test_insurer_profile_selects_sum_insured_on_the_population_prior():
    sector_cfg = {"label": "Insurer", "exposure_measure": {"cell_field": "gross_carrying_amount_eur", "label": "Sum insured", "prior": "population_exposure"}}
    m = exposure_measure(sector_cfg)
    assert m == {"cell_field": "gross_carrying_amount_eur", "label": "Sum insured", "prior": POPULATION, "prior_label": PRIOR_LABEL[POPULATION]}


def test_bank_profile_selects_carrying_amount_on_the_scored_land_prior():
    sector_cfg = {"label": "Bank", "exposure_measure": {"cell_field": "gross_carrying_amount_eur", "label": "Gross carrying amount", "prior": "scored_land"}}
    m = exposure_measure(sector_cfg)
    assert m["label"] == "Gross carrying amount" and m["prior"] == SCORED_LAND


def test_missing_profile_falls_back_to_the_default_field_and_scored_land():
    m = exposure_measure(None)
    assert m["cell_field"] == DEFAULT_FIELD
    assert m["prior"] == SCORED_LAND
    assert m["label"]              # some label, derived — never blank


def test_profile_without_explicit_exposure_measure_derives_a_label_from_intake_or_metrics():
    sector_cfg = {"label": "REIT", "intake": {"submission": {"cell_fields": [
        {"id": "gross_carrying_amount_eur", "label": "Property value (€)"}]}}}
    m = exposure_measure(sector_cfg)
    assert m["cell_field"] == "gross_carrying_amount_eur"
    assert m["label"] == "Property value"     # "(€)" suffix stripped
    assert m["prior"] == SCORED_LAND           # no prior named → default


def test_unknown_prior_name_is_an_error_not_a_silent_fallback():
    sector_cfg = {"label": "Bogus", "exposure_measure": {"prior": "not_a_real_prior"}}
    with pytest.raises(ValueError, match="unknown plausibility prior"):
        exposure_measure(sector_cfg)


def test_share_of_uses_the_measure_named_field():
    measure = {"cell_field": "sum_insured_eur"}
    assert share_of({"sum_insured_eur": 1000, "sensitive_physical_eur": 250}, measure) == 0.25
    # a cell without the named field, or with it non-positive, has no share — never a guess
    assert share_of({"sensitive_physical_eur": 250}, measure) is None
    assert share_of({"sum_insured_eur": 0, "sensitive_physical_eur": 250}, measure) is None
    assert share_of({"sum_insured_eur": "not-a-number", "sensitive_physical_eur": 250}, measure) is None


def test_share_of_clamps_to_zero_one():
    measure = {"cell_field": "sum_insured_eur"}
    assert share_of({"sum_insured_eur": 100, "sensitive_physical_eur": 500}, measure) == 1.0


def test_weighted_rows_weights_each_point_by_its_own_measure_and_excludes_what_it_cannot_use():
    points = [
        {"country": "ES", "region": "ES11", "score": 85.0, "hazard": "flood", "sum_insured_eur": 1_000_000},   # High/Very high → sensitive
        {"country": "ES", "region": "ES12", "score": 10.0, "hazard": "flood", "sum_insured_eur": 500_000},     # low → not sensitive
        {"country": "ES", "region": "ES13", "score": 85.0, "hazard": "flood", "sum_insured_eur": None},        # no measure → excluded
        {"country": None, "region": None, "score": 85.0, "hazard": "flood", "sum_insured_eur": 200_000},       # unlocated → excluded
        {"country": "ES", "region": "ES14", "score": None, "hazard": "flood", "sum_insured_eur": 300_000},     # unscored → excluded
    ]
    rows, counts = weighted_rows(points, measure_field="sum_insured_eur")
    assert len(rows) == 2
    assert rows[0] == ("ES", "ES11", True, "flood", 1_000_000.0)
    assert rows[1] == ("ES", "ES12", False, "flood", 500_000.0)
    assert counts == {"n_points": 5, "n_used": 2, "n_without_measure": 1, "n_unlocated": 1, "n_unscored": 1}


def test_weighted_rows_excludes_non_positive_measure():
    points = [{"country": "ES", "region": "ES11", "score": 5.0, "hazard": "flood", "sum_insured_eur": -10}]
    rows, counts = weighted_rows(points, measure_field="sum_insured_eur")
    assert rows == [] and counts["n_without_measure"] == 1
