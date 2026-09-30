"""ESRS water-stress definitions read off WRI Aqueduct basins (services/reference/aqueduct.py), on synthetic basins in a
rolled-back transaction: WRI's own category codes, an exact point-in-polygon placement, each version's definition
criterion by criterion — 'Arid and Low Water Use' is its own class, and a criterion no dataset supports is not assessed."""
from __future__ import annotations

import pytest
from shapely import wkb
from shapely.geometry import box
from sqlalchemy import text

from services.reference.aqueduct import classify

pytestmark = pytest.mark.integration
OLD, NEW = "dr_2023_2772_as_2025_1416", "dr_2026_1563"


def _basin(s, load, sid, x0, y0, bws_cat, bws_label, bwd_cat, bwd_label):
    g = box(x0, y0, x0 + 1, y0 + 1)
    s.execute(text("""INSERT INTO aqueduct_basins (load_id, string_id, bws_raw, bws_cat, bws_label, bwd_raw, bwd_cat, bwd_label,
                                                   minx, miny, maxx, maxy, geom_wkb)
                      VALUES (CAST(:l AS uuid), :s, 0, :bc, :bl, 0, :dc, :dl, :x0, :y0, :x1, :y1, :w)"""),
              {"l": load, "s": sid, "bc": bws_cat, "bl": bws_label, "dc": bwd_cat, "dl": bwd_label,
               "x0": x0, "y0": y0, "x1": x0 + 1, "y1": y0 + 1, "w": wkb.dumps(g)})


def test_the_definitions_read_criterion_by_criterion(session_rolled_back):
    s = session_rolled_back
    s.execute(text("UPDATE aqueduct_loads SET retired_at = now() WHERE retired_at IS NULL"))
    load = s.execute(text("INSERT INTO aqueduct_loads (version, source) VALUES ('probe', 'probe') RETURNING load_id::text")).scalar()
    _basin(s, load, "high", 100, 10, 3, "High (40-80%)", 1, "Low - Medium (5-25%)")
    _basin(s, load, "medium", 102, 10, 2, "Medium - High (20-40%)", 3, "High (50-75%)")
    _basin(s, load, "arid", 104, 10, -1, "Arid and Low Water Use", -1, "Arid and Low Water Use")

    high = classify(s, 10.5, 100.5, OLD)
    assert high["in_area"] is True and high["criteria"] == [{"id": "bws_high", "met": True, "category": 3, "label": "High (40-80%)"}]
    assert classify(s, 10.5, 102.5, OLD)["in_area"] is False               # 20-40 % is not high water stress (2023)
    new = classify(s, 10.5, 102.5, NEW)                                     # 2026: baseline water DEPLETION is High
    assert new["in_area"] is True and [c["met"] for c in new["criteria"]] == [False, None, True, None]
    arid = classify(s, 10.5, 104.5, OLD)
    assert arid["in_area"] is None and arid["criteria"][0]["met"] is None   # its own class, never read as a percentage
    # 2026, nothing met on the two assessable criteria: not determinable, because (b) and (d) cannot be assessed
    assert classify(s, 10.5, 100.5, NEW)["in_area"] is True
    none_met = classify(s, 10.5, 104.5, NEW)
    assert none_met["in_area"] is None and "not every criterion" in none_met["note"]
    assert classify(s, 50.0, 50.0, OLD)["status"] == "no_data"               # outside every basin
