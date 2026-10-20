"""The European flood loss test (data/reference/loss_protocol.json 'europe_loss_test'): the registered selection is the
one the code applies, the curve's mean over a zone is exact from the interval sums, the defence level is the median
over the cells the protection map holds a period for, and the sampler's zone read counts what it says."""
from __future__ import annotations

import numpy as np
import pytest

from services.loss import curves, engine, protection
from services.loss import europe_loss_test as T

rasterio = pytest.importorskip("rasterio")


def test_the_code_applies_the_registered_selection():
    p = T.protocol()
    assert "'River' or 'River/Coastal'" in p["selection"] and T.TYPES == ("River", "River/Coastal")
    assert "1990–2020" in p["selection"] and T.YEARS == (1990, 2020)
    assert f"'{T.ASSETS}', 50th percentile" in p["data"]["exposure"] and T.PERCENTILE == 50
    assert f"'{T.LOSS}'" in p["data"]["events"] and f"'{T.REGIONS}'" in p["data"]["events"]
    assert T.OUTLINES.name in p["data"]["regions"] and "v2010" in T.REGIONS        # one region set throughout
    assert "1-in-100-year" in p["modelled"] and T.ZONE_RP == 100
    assert "÷ 31 years" in p["observed"] and T.YEARS[1] - T.YEARS[0] + 1 == 31
    fam = curves.families()[T.FAMILY]
    assert all(any(c["key"] == k for c in fam["curves"]) for k in p["curves"])


def test_the_run_refuses_files_that_do_not_share_one_region_set():
    """E301: on the events' v2021 lists 188 regions had no exposure; the run now refuses such a mismatch."""
    assert T.region_set_gaps([], {"A1", "B2"}, {"A1", "B2"}) == []
    assert len(T.region_set_gaps(["C3"], {"A1"}, {"A1"})) == 1
    assert len(T.region_set_gaps([], {"A1", "B2"}, {"A1", "D4"})) == 2      # each side's strays named


def test_an_outline_whose_ring_touches_itself_is_repaired_to_the_same_area():
    """E302: 1,068 of HANZE's 1,422 outlines have rings that touch themselves; clipping one stopped the pass over the
    maps. The repair keeps the area; a ring that truly crosses itself has no clear area and is refused."""
    from shapely.geometry import Polygon
    touch = Polygon([(0, 0), (4, 0), (4, 4), (2, 4), (3, 2), (1, 2), (2, 4), (0, 4)])   # touches itself at (2, 4)
    assert not touch.is_valid
    fixed = T.valid_outline(touch)
    assert fixed.is_valid and fixed.area == pytest.approx(touch.area) == pytest.approx(14.0)
    assert fixed.intersection(Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])).area == pytest.approx(1.0)
    with pytest.raises(ValueError):
        T.valid_outline(Polygon([(0, 0), (2, 2), (2, 0), (0, 2)]))                   # a bow tie: crosses at (1, 1)


def test_the_timestep_is_the_years_own_else_the_nearest_earlier():
    steps = [1985, 1990, 1995, 2000, 2001]
    assert T.step_for(1990, steps) == 1990
    assert T.step_for(1993, steps) == 1990
    assert T.step_for(2001, steps) == 2001
    assert T.step_for(1980, steps) is None


def test_eu_country_codes_are_read_as_iso():
    assert T.country_of("EL301") == "GR" and T.country_of("UKI31") == "GB" and T.country_of("DE111") == "DE"


@pytest.mark.parametrize("key", ["jrc_huizinga_2017:residential:150", "jrc_huizinga_2017:industrial:150"])
def test_the_mean_over_the_zone_from_interval_sums_equals_the_curve_cell_by_cell(key):
    cv = next(c for c in curves.families()[T.FAMILY]["curves"] if c["key"] == key)
    edges = T.edges_for([cv])
    rng = np.random.default_rng(3)
    depth = np.concatenate([rng.uniform(0.051, 9.0, 4000), np.zeros(1000)])     # 1,000 dry zone cells
    wet = depth > 0.05
    b = np.searchsorted(edges, depth[wet], side="right") - 1
    counts = np.bincount(b, minlength=len(edges)).tolist()
    sums = np.bincount(b, weights=depth[wet], minlength=len(edges)).tolist()
    direct = sum(curves.ratio(cv["points"], d) for d in depth[wet]) / len(depth)
    assert T.mean_fraction(counts, sums, len(depth), cv["points"], edges) == pytest.approx(direct, rel=1e-12)


def test_a_curve_not_starting_at_depth_zero_is_refused():
    with pytest.raises(ValueError):
        T.edges_for([{"key": "x", "points": [[0.2, 0.0], [1.0, 0.5]]}])


def test_the_defence_level_is_the_median_over_cells_holding_a_period():
    assert T.design_period([[-1.0, 50], [10.0, 1], [100.0, 2]]) == (100.0, 3)        # no-data cells left out
    assert T.design_period([[10.0, 2], [100.0, 2]]) == (55.0, 4)                     # even: mean of the middle two
    assert T.design_period([[-1.0, 9]]) == (None, 0)                                 # none held: undefended
    assert T.design_period([]) == (None, 0)


def test_modelled_reads_the_engine_and_the_protection_rule():
    edges = [0.0, 0.5, 1.0]
    pts = [[0.0, 0.0], [0.5, 0.25], [1.0, 0.4]]
    rps = [10, 100, 500]
    p = {"zone": 10, "counts": [[0, 0, 0], [0, 10, 0], [0, 0, 10]], "sums": [[0, 0, 0], [0, 7.5, 0], [0, 0, 20.0]],
         "lookup": [[100.0, 4]], "off": 0}
    m = T.modelled(p, pts, edges, rps)
    fr = {10: 0.0, 100: 0.325, 500: 0.4}                     # 0.75 m → 0.325; beyond the last point the ratio holds
    assert m["fraction_at_rp"] == {"10": 0.0, "100": 0.325, "500": 0.4}
    assert m["ead_undefended"] == pytest.approx(engine.eal(fr))
    assert m["ead"] == pytest.approx(protection.defended_eal(fr, 100.0)) and m["design_rp_years"] == 100.0
    assert T.modelled({**p, "lookup": []}, pts, edges, rps)["ead"] == pytest.approx(engine.eal(fr))


def test_the_zone_read_counts_zone_cells_bins_depths_and_reads_the_lookup(tmp_path, monkeypatch):
    from rasterio.transform import from_origin

    from services.geo import raster_sampler as rs
    monkeypatch.setenv("RASTER_SAMPLER_INPROCESS", "1")

    def write(name, data, crs="EPSG:4326", tr=from_origin(0.0, 10.0, 1.0, 1.0), nodata=-9999.0):
        p = tmp_path / name
        with rasterio.open(p, "w", driver="GTiff", height=data.shape[0], width=data.shape[1], count=1,
                           dtype=data.dtype, crs=crs, transform=tr, nodata=nodata) as dst:
            dst.write(data, 1)
        return str(p)
    zone = np.full((10, 10), -9999.0, dtype="float32")
    zone[1:4, 1:4] = 1.2                                   # 9 wet cells in shape 1's square
    zone[2, 2] = 0.04                                      # ... one of them is raster noise: dry
    zone[1, 1] = 3.5                                       # ... one deeper
    water = np.zeros((10, 10), dtype="float64")
    water[3, 3] = 1                                        # ... one a permanent water body
    rp10 = np.full((10, 10), -9999.0, dtype="float32")
    rp10[1, 1:4] = 0.3                                     # three of the zone cells wet at the frequent period
    look = np.array([[5.0, 50.0], [-1.0, 200.0]], dtype="float32")   # 5°-square cells, another grid
    paths = {"z": write("z.tif", zone), "w": write("w.tif", water), "r": write("r.tif", rp10),
             "l": write("l.tif", look, tr=from_origin(0.0, 10.0, 5.0, 5.0), nodata=-1.0)}
    sq = {"type": "Polygon", "coordinates": [[(1, 9), (4, 9), (4, 6), (1, 6), (1, 9)]]}
    got = rs.zone_bins(paths["z"], (0, 0, 10, 10), [(sq, 1)], [paths["r"], paths["z"]], [0.0, 0.5, 1.0, 2.0], 0.05,
                       exclude={"path": paths["w"], "value": 1}, lookup=paths["l"])
    s = got[1]
    assert s["zone"] == 7                                  # 9 − the noise cell − the water cell
    assert s["counts"][0] == [3, 0, 0, 0] and s["sums"][0] == pytest.approx([0.9, 0, 0, 0])
    assert s["counts"][1] == [0, 0, 6, 1] and s["sums"][1] == pytest.approx([0, 0, 7.2, 3.5])
    assert s["lookup"] == [[5.0, 7]] and s["off"] == 0      # every zone cell centre in the top-left 5° cell
    assert rs.zone_bins(paths["z"], (6, 6, 4, 4), [(sq, 1)], [paths["r"]], [0.0], 0.05) == {}
