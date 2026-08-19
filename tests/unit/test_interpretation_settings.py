"""The governed interpretation-switch schema — every switch has a default that reproduces today's number,
values are validated against the schema, and the catalog is sector-scoped. Pure — no DB."""
import pytest

from services.calc_settings import (
    DEFAULTS,
    INTERPRETATION_SCHEMA,
    interpretation_catalog,
    validate_interpretation,
)


def test_defaults_reproduce_todays_numbers():
    # the shipped hard-coded values are the defaults, so an un-configured org is unchanged
    assert DEFAULTS["pml_return_period"] == 250
    assert DEFAULTS["insurance_expense_ratio"] == 0.25
    assert DEFAULTS["insurance_profit_margin"] == 0.05
    assert DEFAULTS["climate_var_dependence"] == "independent"
    assert DEFAULTS["resourcing_reallocation_cap_pct"] == 30
    assert DEFAULTS["adaptation_scenario"] == "reference"
    # legacy typed methods still present
    assert DEFAULTS["severity_model"] == "universal"


def test_validate_accepts_allowed_and_coerces_type():
    assert validate_interpretation("pml_return_period", "200") == 200      # Solvency II, coerced from str
    assert validate_interpretation("insurance_expense_ratio", 0.3) == 0.3
    assert validate_interpretation("climate_var_dependence", "additive") == "additive"


def test_validate_rejects_out_of_set_range_and_unknown():
    with pytest.raises(ValueError):
        validate_interpretation("pml_return_period", 999)          # not in the allowed set
    with pytest.raises(ValueError):
        validate_interpretation("insurance_expense_ratio", 0.9)    # above max
    with pytest.raises(ValueError):
        validate_interpretation("climate_var_dependence", "nope")  # not an allowed enum
    with pytest.raises(ValueError):
        validate_interpretation("does_not_exist", 1)               # unknown switch


def test_catalog_is_sector_scoped():
    ins = {c["key"] for c in interpretation_catalog("insurer")}
    reit = {c["key"] for c in interpretation_catalog("reit")}
    assert "pml_return_period" in ins and "pml_return_period" not in reit
    assert "adaptation_scenario" in reit and "adaptation_scenario" not in ins
    # every catalog entry carries the UI fields
    for c in interpretation_catalog():
        assert c["label"] and c["description"] and "default" in c


def test_schema_defaults_and_catalog_are_consistent():
    for key, spec in INTERPRETATION_SCHEMA.items():
        # the default must itself validate
        assert validate_interpretation(key, spec["default"]) == spec["default"]
