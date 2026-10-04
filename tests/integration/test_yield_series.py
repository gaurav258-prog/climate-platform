"""E156: the one reader of the crop-yield store — an event is counted once, from ONE source per crop and country (by
the stated precedence); a regional series never joins its country's national one; USDA FAS (market years) is never
chosen for a history; a source holding several regional series is refused unless the region is named. Rolled back."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from ml.features import yield_series as Y

pytestmark = pytest.mark.integration
CROP = "Test crop (E156)"


def _row(s, country, year, source, prod, yoy=None, region=""):
    s.execute(text("""INSERT INTO crop_yield_observations (commodity, country, region_code, season_year, production_tonnes,
                      yoy_change_pct, source) VALUES (:c, :o, :r, :y, :p, :yoy, :s)"""),
              {"c": CROP, "o": country, "r": region, "y": year, "p": prod, "yoy": yoy, "s": source})


def test_one_source_per_crop_and_country(session_rolled_back):
    s = session_rolled_back
    for src in ("FAOSTAT QCL bulk", "EUROSTAT apro_cpsh1", "USDA FAS PSD"):          # the same collapse, three sources
        _row(s, "ES", 2012, src, 500.0, -50.0)
    _row(s, "ES", 2012, "EUROSTAT apro_cpsh1", 90.0, -40.0, region="ES61")           # a region: never national
    _row(s, "PT", 2012, "EUROSTAT apro_cpsh1", 80.0, -30.0)                           # FAOSTAT holds no PT series
    _row(s, "MA", 2012, "USDA FAS PSD", 70.0, -20.0)                                  # only FAS: never a history
    got = sorted((r["country"], r["source"]) for r in Y.shocks(s, -5) if r["commodity"] == CROP)
    assert got == [("ES", "FAOSTAT QCL bulk"), ("PT", "EUROSTAT apro_cpsh1")]
    assert Y.national(s, CROP, "ES")[0] == "FAOSTAT QCL bulk" and Y.national(s, CROP, "MA") == (None, {})
    assert Y.by_country(s, CROP, "EUROSTAT apro_cpsh1") == {"ES": {2012: 500.0}, "PT": {2012: 80.0}}
    assert Y.series(s, CROP, "ES", "EUROSTAT apro_cpsh1", "ES61") == {2012: 90.0}
    with pytest.raises(Y.SeriesError, match="name the region"):
        Y.series(s, CROP, "ES", "EUROSTAT apro_cpsh1", region_code=None)
    assert set(Y.every_series(s, CROP, "ES")) == {"FAOSTAT QCL bulk", "EUROSTAT apro_cpsh1", "USDA FAS PSD",
                                                  "EUROSTAT apro_cpsh1 · ES61"}


def test_every_reviewed_source_states_its_role():
    """E157: each reviewed yield source is in exactly one role of data/reference/yield_series.json — chosen by
    precedence, never in a history, or read only when named — so a new source never joins histories by accident."""
    from services.reference.yield_sources import all_sources
    rules = Y.rules()
    roles = [set(rules["national_precedence"]), set(rules["never_in_history"]), set(rules["named_only"])]
    for ys in all_sources():
        assert sum(ys.label() in r for r in roles) == 1, f"{ys.label()} must state exactly one role"


def test_every_region_held_is_in_the_region_reference(session_rolled_back):
    """E157: every region code in the yield store is a region of the reference (ISO 3166-2 from the national
    authority's list, or NUTS)."""
    from services.reference import regions
    held = session_rolled_back.execute(text(
        "SELECT DISTINCT region_code FROM crop_yield_observations WHERE region_code <> ''")).scalars().all()
    assert held and not [c for c in held if not regions.known(c)]
