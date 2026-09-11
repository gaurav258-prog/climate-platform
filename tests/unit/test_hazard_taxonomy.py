"""The EU Taxonomy hazard registry is a compliance surface — its shape must not drift silently."""
from __future__ import annotations

from core.hazard_taxonomy import (
    EU_TAXONOMY,
    EXTRA_CHANNELS,
    MaturityTier,
    coverage_summary,
    eu_hazards_by_family,
)
from core.types import HazardType
from services.intelligence.coverage import eu_taxonomy_coverage


def test_exactly_28_hazards():
    """Appendix A defines 28 physical climate hazards — no more, no fewer."""
    assert len(EU_TAXONOMY) == 28


def test_family_counts():
    """The four families sum to 28 in their Appendix-A sizes."""
    counts = {k: len(v) for k, v in eu_hazards_by_family().items()}
    assert counts == {"temperature": 7, "wind": 4, "water": 10, "solid_mass": 7}


def test_ids_unique():
    ids = [h.id for h in EU_TAXONOMY]
    assert len(ids) == len(set(ids))


def test_every_internal_channel_is_mapped():
    """Every canonical HazardType must appear on the EU list or as an explicit extra — nothing orphaned."""
    referenced = {c for h in (*EU_TAXONOMY, *EXTRA_CHANNELS) for c in h.internal}
    assert set(HazardType) - referenced == set()


def test_tiers_are_valid_and_roadmap_has_no_channel():
    for h in EU_TAXONOMY:
        assert isinstance(h.tier, MaturityTier)
        # a live hazard is one that has a phase == "now"; a roadmap hazard must not claim a live channel
        if h.tier is MaturityTier.ROADMAP:
            assert h.phase != "now" and h.internal == ()
        else:
            assert h.phase == "now" and h.internal != ()


def test_summary_reconciles():
    s = coverage_summary()
    assert s["total"] == 28
    assert s["covered"] + s["roadmap"] == 28
    assert sum(s["by_tier"].values()) == 28
    assert sum(s["by_phase"].values()) == s["roadmap"]


def test_api_serialization_shape():
    cov = eu_taxonomy_coverage()
    assert sum(len(f["hazards"]) for f in cov["families"]) == 28
    assert len(cov["families"]) == 4
    assert len(cov["extra_channels"]) == len(EXTRA_CHANNELS) == 3
    # each serialized hazard carries the load-bearing fields
    first = cov["families"][0]["hazards"][0]
    assert {"id", "name", "family", "nature", "tier", "phase", "source", "internal"} <= set(first)


def test_by_nature_tier_is_context_only():
    """A by-nature hazard has nothing observed to backtest against: it never headlines and never claims calibration."""
    from core.hazard_relevance import is_headline_eligible
    from core.hazard_taxonomy import CALIBRATED_VALIDATION, EU_TAXONOMY, MaturityTier, screening_status
    by_nature = [h for h in EU_TAXONOMY if h.tier is MaturityTier.BY_NATURE]
    assert {h.id for h in by_nature} == {"changing_temperature", "temperature_variability", "changing_wind",
                                         "changing_precipitation", "precipitation_variability", "ocean_acidification"}
    for h in by_nature:
        assert h.id not in CALIBRATED_VALIDATION and h.source.startswith("By nature:")
        for ch in h.internal:
            assert not is_headline_eligible(ch.value, "buildings"), h.id
    # a screening hazard states whether it was tested and failed or still lacks a target; other tiers carry no status
    assert screening_status("storm", MaturityTier.SCREENING) == "tested_negative"
    assert screening_status("solifluction", MaturityTier.SCREENING) == "no_target_yet"
    assert screening_status("flood", MaturityTier.CALIBRATED) is None
