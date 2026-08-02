"""Climate-hazard scope (audit T8) — every climate-attributable hazard must be in CLIMATE.

ESRS E1 and EU-Taxonomy climate-adaptation both scope assets via hazard_scope.CLIMATE. A climate
hazard missing from that set is silently dropped from BOTH regulatory reports — the exact failure the
consolidated review caught for coastal_flood (sea-level rise). This guard stops it recurring: every
climate-driven HazardType must be classified climate; only the geophysical ones may be 'other'.
"""
from core.types import HazardType
from services.intelligence.hazard_scope import CLIMATE, hazard_class

# geophysical / non-climate hazards legitimately outside the climate scope
NON_CLIMATE = {"seismic", "volcanic", "pollution"}


def test_coastal_flood_is_a_climate_hazard():
    assert "coastal_flood" in CLIMATE
    assert hazard_class("coastal_flood") == "acute"   # sea-level rise is event-driven + climate-attributable


def test_every_climate_hazardtype_is_in_scope():
    for h in HazardType:
        if h.value in NON_CLIMATE:
            assert hazard_class(h.value) == "other", f"{h.value} should be non-climate"
        else:
            assert h.value in CLIMATE, f"climate hazard {h.value} is missing from hazard_scope.CLIMATE"
