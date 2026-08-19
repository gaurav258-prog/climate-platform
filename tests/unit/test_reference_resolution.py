"""Reference-resolution guard clauses — these must reject malformed input BEFORE
any network call, so a bad ISIN is a cheap 'None', never a GLEIF round-trip or a
fabricated issuer. Pure (no network, no DB)."""
from ml.regulatory.sfdr_pai import (
    COUNTRY_GHG_INTENSITY_TCO2E_PER_MEUR,
    DEFAULT_COUNTRY_INTENSITY,
    MANDATORY_PAI_INDICATORS,
    _real_estate_indicators,
    _sovereign_indicators,
)
from services.reference import gleif


def test_resolve_isin_rejects_malformed_without_network():
    # 12-alphanumeric is the ISIN shape; anything else returns None immediately.
    assert gleif.resolve_isin("") is None
    assert gleif.resolve_isin("SHORT") is None
    assert gleif.resolve_isin("TOOLONG12345678") is None
    assert gleif.resolve_isin("US03783310!!") is None  # non-alphanumeric


def test_fetch_lei_rejects_malformed_without_network():
    assert gleif.fetch_lei("") is None
    assert gleif.fetch_lei("NOT-A-LEI") is None
    assert gleif.fetch_lei("X" * 21) is None  # LEI is exactly 20 chars


def test_all_14_mandatory_investee_indicators_present():
    numbers = [n for (n, _a, _m, _u) in MANDATORY_PAI_INDICATORS]
    assert numbers == list(range(1, 15))  # 1..14, none dropped


def test_real_estate_not_applicable_for_securities_fund():
    re = _real_estate_indicators({"has_real_estate": False})
    assert [i["number"] for i in re] == [17, 18]
    assert all(i["method"] == "not_applicable" for i in re)


def test_sovereign_indicator_15_computes_from_country_intensity():
    de = COUNTRY_GHG_INTENSITY_TCO2E_PER_MEUR["DE"]
    inds = _sovereign_indicators({"sovereign_ghg_intensity": de})
    pai15 = next(i for i in inds if i["number"] == 15)
    assert pai15["method"] == "computed" and pai15["value"] == de
    # No sovereign exposure → indicator 15 becomes a disclosed gap, not a zero.
    gap = _sovereign_indicators({"sovereign_ghg_intensity": None})
    assert next(i for i in gap if i["number"] == 15)["method"] == "not_available"


def test_country_default_intensity_is_defined():
    assert DEFAULT_COUNTRY_INTENSITY > 0
