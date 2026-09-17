"""Pure-logic tests for the GTN-P permafrost borehole backtest (no network, no DB)."""
from __future__ import annotations

import csv

from services.validation.validators.permafrost_gtnp import _coldness, load_boreholes


def test_coldness_flips_sign():
    assert _coldness(-8.4) == 8.4      # cold, stable ground -> high coldness
    assert _coldness(2.1) == -2.1      # thawed ground (above 0 degC) -> negative coldness


def test_load_boreholes_reads_csv_and_builds_h3_cell(tmp_path):
    p = tmp_path / "borehole_magt.csv"
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["borehole_id", "lat", "lon", "country", "permafrost_zone",
                                          "depth_m", "magt_c", "n_obs", "n_years", "first_year", "last_year"])
        w.writeheader()
        w.writerow({"borehole_id": 1119, "lat": 47.18934268, "lon": 12.68529504, "country": "AT",
                    "permafrost_zone": "Mountain Permafrost", "depth_m": 10.0, "magt_c": -1.25,
                    "n_obs": 3000, "n_years": 8, "first_year": 2016, "last_year": 2024})
    rows = load_boreholes(p)
    assert len(rows) == 1
    r = rows[0]
    assert r["borehole_id"] == 1119 and r["country"] == "AT"
    assert r["magt_c"] == -1.25 and r["depth_m"] == 10.0
    assert len(r["h3_cell"]) > 0


def test_load_boreholes_missing_file_returns_empty(tmp_path):
    assert load_boreholes(tmp_path / "nope.csv") == []
