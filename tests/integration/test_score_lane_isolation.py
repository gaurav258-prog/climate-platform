"""score_lane isolation — a nowcast must never retire a standing climatology.

THE REGRESSION THIS GUARDS (real, 2026-07). canonical_scores retired prior scores on
(h3_cell, hazard_type, scenario) with no notion of WHICH model or what for. So the
public "is it hot today" lookup wrote 0.0 over cocoa's calibrated seasonal heat score
of 74.2 for the Côte d'Ivoire belt — silently invalidating the crop's entire backtest.
The crop engine then fell back to the next-worst hazard (wildfire) and kept its
'backtested' badge.

The standing lane (climatology → portfolio numbers, calibrations, backtests) and the
nowcast lane (live reading → public lookup, parametric triggers) must be isolated.
Requires PostgreSQL.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from core.db.session import get_session

CELL = "88750e46e5fffff"   # a real cocoa-belt cell shape; test rows use a synthetic cell
TEST_CELL = "88ffffffffffff9"


def _insert(s, lane, model, score, horizon="current"):
    s.execute(text("""
        INSERT INTO canonical_scores
            (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
             risk_score, risk_bucket, model_version, data_vintage, scored_at,
             valid_from, valid_to, score_lane)
        VALUES (gen_random_uuid(), :cell, 8, 'heat_acute', 'baseline', :h,
                :score, 'M', :mv, now(), now(), now(), NULL, :lane)
    """), {"cell": TEST_CELL, "h": horizon, "score": score, "mv": model, "lane": lane})


def _current(s, lane):
    return s.execute(text("""
        SELECT risk_score FROM canonical_scores
        WHERE h3_cell = :c AND hazard_type='heat_acute' AND scenario='baseline'
          AND time_horizon='current' AND score_lane = :lane AND valid_to IS NULL
    """), {"c": TEST_CELL, "lane": lane}).scalars().all()


@pytest.mark.integration
def test_nowcast_retirement_does_not_touch_standing_score():
    """Retiring within the nowcast lane (what the on-demand scorers do) must leave the
    standing climatology live and untouched."""
    try:
        with get_session() as s:
            _insert(s, "standing", "heat-climatology-v1-seasonal", 74.2)
            _insert(s, "nowcast", "heat-climatology-v1-ondemand", 12.0)

        # This is exactly the statement score_heat_on_demand.py runs — lane-scoped.
        with get_session() as s:
            s.execute(text("""
                UPDATE canonical_scores SET valid_to = :now
                WHERE hazard_type='heat_acute' AND scenario='baseline' AND time_horizon='current'
                  AND score_lane='nowcast' AND valid_to IS NULL AND h3_cell = ANY(:cells)
            """), {"now": datetime.now(timezone.utc), "cells": [TEST_CELL]})
            _insert(s, "nowcast", "heat-climatology-v1-ondemand", 0.0)

        with get_session() as s:
            standing = _current(s, "standing")
            nowcast = _current(s, "nowcast")

        # The calibrated climatology survives the nowcast entirely.
        assert [float(x) for x in standing] == [74.2]
        assert [float(x) for x in nowcast] == [0.0]
    finally:
        with get_session() as s:
            s.execute(text("ALTER TABLE canonical_scores DISABLE TRIGGER prevent_delete_canonical_scores"))
            s.execute(text("DELETE FROM canonical_scores WHERE h3_cell = :c"), {"c": TEST_CELL})
            s.execute(text("ALTER TABLE canonical_scores ENABLE TRIGGER prevent_delete_canonical_scores"))


@pytest.mark.integration
def test_supply_view_reads_standing_lane_only():
    """The crop engine must never see a nowcast: a live reading cannot drive COGS-at-risk."""
    with get_session() as s:
        # standing + nowcast legitimately coexist for the same key, so joining back by key
        # would false-positive. Assert on what the view actually surfaces: its model_version.
        leaked = s.execute(text("""
            SELECT count(*) FROM v_sc_plot_physical_risk v
            WHERE strpos(lower(v.model_version), 'on-demand') > 0
               OR strpos(lower(v.model_version), 'ondemand') > 0
        """)).scalar()
    assert leaked == 0


@pytest.mark.integration
def test_cocoa_driver_hazard_is_scored_on_its_plots():
    """Cocoa's calibrated driver (heat_acute, seasonal climatology) must actually be
    readable on its plots — otherwise the gate withholds its € and the marquee crop is
    dark. This is what the plot-snapping guarantees."""
    with get_session() as s:
        rows = s.execute(text("""
            SELECT p.country, count(*) AS n
            FROM   sc_sourcing_plots p
            JOIN   sc_commodities co ON co.commodity_id = p.commodity_id
            JOIN   v_sc_plot_physical_risk v
              ON   v.plot_id = p.plot_id AND v.scenario='baseline' AND v.time_horizon='current'
             AND   v.hazard_type = 'heat_acute'
            WHERE  co.name = 'Cocoa'
            GROUP  BY p.country
        """)).mappings().all()
    by_country = {r["country"]: r["n"] for r in rows}
    # Both cocoa origins must see their driver hazard.
    assert by_country.get("CI", 0) > 0, "Côte d'Ivoire cocoa plots cannot see heat_acute"
    assert by_country.get("GH", 0) > 0, "Ghana cocoa plots cannot see heat_acute"
