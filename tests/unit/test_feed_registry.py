"""The feed registry names a real source for every hazard channel we score, and pinned dataset releases are never
ticked by the scheduler as if they had been refreshed."""
from __future__ import annotations

from core.types import HazardType
from services.data.feeds import FEEDS, HAZARD_FEEDS

BY_KEY = {f["key"]: f for f in FEEDS}


def test_every_hazard_channel_maps_to_registered_feeds():
    unmapped = [h.value for h in HazardType if not HAZARD_FEEDS.get(h.value)]
    assert not unmapped, f"hazard channels with no source feed: {unmapped}"
    for hz, keys in HAZARD_FEEDS.items():
        assert all(k in BY_KEY for k in keys), f"{hz} maps to an unknown feed"
        assert all(BY_KEY[k]["maturity"] != "planned" for k in keys), f"{hz} claims a feed that is not in production"


def test_pinned_releases_are_not_auto_refreshed():
    releases = [f for f in FEEDS if f["maturity"] == "release"]
    assert releases and not any(f["auto_refresh"] for f in releases)


def test_flood_is_sourced_from_the_jrc_maps_not_the_runoff_proxy():
    assert HAZARD_FEEDS["flood"][0] == "jrc_flood_maps"
    assert "flood" not in {k for keys in HAZARD_FEEDS.values() for k in keys}
    # the runoff proxy no longer drives a published score, so its refresh must not invalidate a filing basis
    assert BY_KEY["flood"]["invalidates_basis"] is False
    assert BY_KEY["jrc_flood_maps"]["invalidates_basis"] is True
