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
    # a money-figure choice has no platform default (E69): not set, the figure that needs it is a named gap
    assert DEFAULTS["pml_return_period"] is None and DEFAULTS["climate_var_dependence"] is None
    assert "resourcing_reallocation_cap_pct" not in DEFAULTS            # a number: the stated method.reallocation_cap
    assert "insurance_expense_ratio" not in DEFAULTS and "severity_model" not in DEFAULTS   # stated method now (E69)


def test_validate_accepts_allowed_and_coerces_type():
    assert validate_interpretation("pml_return_period", "200") == 200      # Solvency II, coerced from str
    assert validate_interpretation("esg_energy_intensity_check_factor", "20") == 20.0
    assert validate_interpretation("climate_var_dependence", "additive") == "additive"


def test_validate_rejects_out_of_set_range_and_unknown():
    with pytest.raises(ValueError):
        validate_interpretation("pml_return_period", 999)          # not in the allowed set
    with pytest.raises(ValueError):
        validate_interpretation("esg_energy_intensity_check_factor", 5000)    # above max
    with pytest.raises(ValueError):
        validate_interpretation("climate_var_dependence", "nope")  # not an allowed enum
    with pytest.raises(ValueError):
        validate_interpretation("does_not_exist", 1)               # unknown switch


def test_catalog_is_sector_scoped():
    ins = {c["key"] for c in interpretation_catalog("insurer")}
    reit = {c["key"] for c in interpretation_catalog("reit")}
    assert "pml_return_period" in ins and "pml_return_period" not in reit
    assert "sii_natcat_uk_other_regions" in ins and "sii_natcat_uk_other_regions" not in reit
    # every catalog entry carries the UI fields
    for c in interpretation_catalog():
        assert c["label"] and c["description"] and "default" in c


def test_schema_defaults_and_catalog_are_consistent():
    for key, spec in INTERPRETATION_SCHEMA.items():
        # a default must itself validate; a money-figure choice has none (E69) — not set is a named gap, and None is never
        # a storable value
        if spec["default"] is None:
            with pytest.raises(ValueError, match="needs a value"):
                validate_interpretation(key, None)
            continue
        assert validate_interpretation(key, spec["default"]) == spec["default"]
