"""insurer_climate's filing form headline block (2026-09-24 fix, platform E2E audit finding #4): it used to
be forced through bank/REIT's field names (total_value_eur/n_scored/n_assets), which insurance's own rollup
never populates (it uses total_sum_insured_eur/n_priced/n_policies/total_expected_annual_loss_eur/
total_technical_premium_eur instead) — silently rendering "Assets scored: 0/0" and
dropping the value/EAL/premium rows on a real, correctly-computed book."""
from services.governance.filing_form import build_form


def _insurer_snap():
    return {
        "rollup": {
            "n_policies": 145, "n_priced": 145,
            "total_sum_insured_eur": 2_450_000_000,
            "total_expected_annual_loss_eur": 18_500_000,
            "total_technical_premium_eur": 26_428_571,
            "value_at_risk_eur": 400_000_000,
            # bank/REIT-only keys are genuinely absent from insurance's rollup — never populated
        },
        "by_hazard": {"windstorm": {"exposed_value_eur": 400_000_000, "n_exposed": 60}},
    }


def _bank_snap():
    return {
        "rollup": {"total_value_eur": 4_176_900_000, "value_at_risk_eur": 2_730_700_000,
                   "pct_value_at_risk": 65.4, "total_discounted_value_eur": 3_900_000_000,
                   "n_scored": 147, "n_assets": 147},
    }


def test_insurer_climate_headline_uses_real_insurance_fields():
    groups = build_form("insurer_climate", _insurer_snap())
    headline = next(g for g in groups if g["group"] == "Headline exposure")
    dps = {d["key"]: d for d in headline["datapoints"]}
    assert dps["book.total_sum_insured_eur"]["value"] == 2_450_000_000
    assert dps["book.total_expected_annual_loss_eur"]["value"] == 18_500_000
    assert dps["book.total_technical_premium_eur"]["value"] == 26_428_571     # a modelled premium, never 'written'
    assert dps["book.sum_insured_at_risk_eur"]["value"] == 400_000_000
    assert "book.total_gross_premium_eur" not in dps and "book.portfolio_loss_ratio_pct" not in dps
    assert dps["book.coverage"]["value"] == "145 / 145"


def test_insurer_climate_never_shows_the_bank_field_names_or_a_fake_zero_zero():
    groups = build_form("insurer_climate", _insurer_snap())
    headline = next(g for g in groups if g["group"] == "Headline exposure")
    keys = {d["key"] for d in headline["datapoints"]}
    assert "book.total_value_eur" not in keys
    assert "book.value_at_risk_eur" not in keys
    coverage = next(d for d in headline["datapoints"] if d["key"] == "book.coverage")
    assert coverage["value"] != "0 / 0"


def test_bank_headline_is_unaffected_by_the_insurer_branch():
    # the located bank book's headline is Pillar 3's (the EU Taxonomy Art. 8 report prints none, E95)
    groups = build_form("bank_p3esg", _bank_snap())
    headline = next(g for g in groups if g["group"] == "Headline exposure")
    dps = {d["key"]: d for d in headline["datapoints"]}
    assert dps["book.total_value_eur"]["value"] == 4_176_900_000
    assert dps["book.value_at_risk_eur"]["value"] == 2_730_700_000
    assert "book.total_sum_insured_eur" not in dps


def test_a_figure_not_computed_stays_on_the_form_as_a_named_gap():
    snap = {"rollup": {"total_value_eur": 1_000_000, "value_at_risk_eur": None, "pct_value_at_risk": None,
                       "total_discounted_value_eur": None, "n_scored": 1, "n_assets": 1,
                       "gap": "not stated: method.at_risk_level"}}
    headline = next(g for g in build_form("bank_p3esg", snap) if g["group"] == "Headline exposure")
    var = next(d for d in headline["datapoints"] if d["key"] == "book.value_at_risk_eur")
    assert var["value"] is None and "method.at_risk_level" in var["note"]
