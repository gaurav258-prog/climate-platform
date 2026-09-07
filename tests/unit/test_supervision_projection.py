"""Shadow-book projections: the anchor set matches the platform's scenario × horizon grid; empty input is a no-op."""
from services.supervision.projection import (
    ANCHORS,
    HORIZONS,
    SCENARIOS,
    project_cells_now,
    schedule_projection,
)


def test_anchor_grid_is_every_scenario_horizon_except_the_real_baseline():
    assert len(ANCHORS) == len(SCENARIOS) * len(HORIZONS) - 1 == 15
    assert ("baseline", "current") not in ANCHORS and ("disorderly_2c", "2030") in ANCHORS


def test_empty_shadow_book_is_a_noop():
    assert project_cells_now([]) == {"cells": 0, "anchors": 15, "cmip6_rows": 0}
    schedule_projection([])   # must not start a thread or touch the DB
