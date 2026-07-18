"""The decomposed world shock — a cyclical crop's honest validation target.

Guards the finding of 2026-07-18: validating a cyclical crop against FAO's RAW world shock
over-attributes to climate, because the raw figure bundles the tree's alternate-bearing cycle
and nets damage against other origins' good years. Olive 2012 is the worked example.

Requires PostgreSQL with the FAOSTAT cyclical-crop origins ingested.
"""
from __future__ import annotations

import pytest

from core.db.session import get_session
from ml.features.world_shock import world_shock


@pytest.mark.integration
def test_olive_2012_three_numbers_diverge():
    """The whole point: for a cyclical, regionally-offsetting crop the raw, net and damage
    world shocks are three DIFFERENT numbers, and only damage is a fair target for a
    damage-only model."""
    with get_session() as s:
        w = world_shock(s, "Olive oil", 2012)

    # raw is the catastrophic-looking headline
    assert w.raw_world_shock_pct is not None and w.raw_world_shock_pct < -14
    # net is far smaller — Spain's loss is offset by other origins' good years
    assert -6 < w.decomposed_net_shock_pct < -2
    # damage (the target) sits between: the real climate loss, no upside credited
    assert -15 < w.decomposed_damage_shock_pct < -10
    # and they are genuinely ordered raw < damage < net (more negative to less)
    assert w.raw_world_shock_pct < w.decomposed_damage_shock_pct < w.decomposed_net_shock_pct


@pytest.mark.integration
def test_olive_2012_coverage_is_high_enough_to_publish():
    """The decomposition is only honest if the origins we can decompose cover most of the
    world crop. Olive must clear a sensible bar."""
    with get_session() as s:
        w = world_shock(s, "Olive oil", 2012)
    assert w.coverage > 0.90, f"olive world coverage only {w.coverage:.0%}"
    assert w.is_publishable(min_coverage=0.85)


@pytest.mark.integration
def test_spain_dominates_the_olive_damage():
    """Sanity on the mechanism: Spain is the origin that actually lost, and its
    climate-attributable drop is far larger than its raw drop is misleading."""
    with get_session() as s:
        w = world_shock(s, "Olive oil", 2012)
    es = next(c for c in w.contributions if c.origin == "ES")
    assert es.usable
    assert es.climate_pct < -25          # a real, large climate loss
    assert es.base_year_share > 0.30     # and a big share of the world crop


@pytest.mark.integration
def test_edge_year_origins_are_refused_not_zeroed():
    """An origin whose target year sits at the edge of its series (trend extrapolated) must be
    excluded from the sum AND from coverage — a gap, never a silent zero."""
    with get_session() as s:
        # 2024 is the last year for most series → an edge year for many origins
        w = world_shock(s, "Olive oil", 2024)
    refused = [c for c in w.contributions if not c.usable and c.reason and "edge" in c.reason]
    # any refused origin must not have been counted into coverage
    assert w.coverage <= 1.0
    for c in refused:
        assert c.climate_pct is None


@pytest.mark.integration
def test_low_coverage_is_not_publishable():
    """A crop we can barely cover must fail the publish gate. Citrus has no FAOSTAT world
    series ingested (EU-only via Eurostat), so its decomposed target is unpublishable."""
    with get_session() as s:
        w = world_shock(s, "Citrus", 2012)
    # either no world series at all, or coverage far below the bar
    assert not w.is_publishable(min_coverage=0.85)
