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
