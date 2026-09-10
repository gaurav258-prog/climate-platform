"""One relevance registry behind every headline: complete, mirrored in the table, and the engine reads it."""
from core.hazard_relevance import (
    ASSET_CLASSES,
    headline_exclude,
    is_headline_eligible,
    registry,
    relevance,
)
from core.types import HAZARD_VALUES


def test_registry_covers_every_hazard_and_both_classes():
    rows = registry()
    assert {(r["hazard_type"], r["asset_class"]) for r in rows} == {(h, c) for h in HAZARD_VALUES for c in ASSET_CLASSES}
    assert all(r["note"] for r in rows if not r["headline"])          # every exclusion states its reason


def test_crop_scales_never_headline_a_building_but_do_headline_a_plot():
    assert not is_headline_eligible("frost", "buildings") and is_headline_eligible("frost", "agriculture")
    assert not is_headline_eligible("soil_water", "buildings") and is_headline_eligible("soil_water", "agriculture")
    assert is_headline_eligible("flood", "buildings") and is_headline_eligible("wildfire", "agriculture")
    # a susceptibility class or a variability percentile is context, never a headline, for any asset class
    for hz in ("subsidence", "landslide", "temp_variability", "precip_variability", "saline_intrusion", "coastal_flood"):
        assert not is_headline_eligible(hz, "buildings") and not is_headline_eligible(hz, "agriculture"), hz
    assert relevance("heat_acute") == {"buildings": False, "agriculture": False}       # a nowcast is never a headline
    assert "heat_acute" in headline_exclude("buildings") and "heat_acute" in headline_exclude("agriculture")
    assert "frost" not in headline_exclude("agriculture") and "subsidence" in headline_exclude("agriculture")
    # anchored and physically thresholded channels are intensity scales for both classes
    assert is_headline_eligible("severe_convective", "buildings") and is_headline_eligible("cold_wave", "buildings")


def test_engine_default_reads_the_registry():
    from services.portfolio_engine import DEFAULT_HEADLINE_EXCLUDE
    assert set(DEFAULT_HEADLINE_EXCLUDE) == set(headline_exclude("buildings")) >= {"heat_acute", "frost", "soil_water"}
