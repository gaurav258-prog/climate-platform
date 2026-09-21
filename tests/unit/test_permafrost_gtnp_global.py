"""Pure-logic tests for the global GTN-P permafrost backtest (no network, no DB)."""
from __future__ import annotations

import csv

from services.validation.validators.permafrost_gtnp_global import load_all, macro_region


def test_macro_region_rule():
    assert macro_region(-62.9, -60.7, "AQ") == "Antarctica/Southern Hemisphere"
    assert macro_region(68.0, 60.0, "RU") == "Russia/Siberia"
    assert macro_region(70.3, -148.7, "US") == "North America"
    assert macro_region(33.0, 91.9, "CN") == "Central Asia/Tibetan Plateau"
    assert macro_region(46.5, 9.8, "CH") == "Europe/Arctic Atlantic"


def _write(p, rows):
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["borehole_id", "lat", "lon", "country", "depth_m", "magt_c"])
        w.writeheader()
        w.writerows(rows)


def test_load_all_unions_and_dedupes(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    _write(a, [{"borehole_id": 1, "lat": 70, "lon": -148, "country": "US", "depth_m": 10, "magt_c": -5}])
    _write(b, [{"borehole_id": 1, "lat": 70, "lon": -148, "country": "US", "depth_m": 10, "magt_c": -5},
               {"borehole_id": 2, "lat": -63, "lon": -60, "country": "AQ", "depth_m": 5, "magt_c": -1}])
    rows = load_all((a, b, tmp_path / "missing.csv"))
    assert [r["borehole_id"] for r in rows] == [1, 2]
    assert rows[0]["region"] == "North America" and rows[1]["region"].startswith("Antarctica")
