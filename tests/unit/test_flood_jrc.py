"""Flood v3 — JRC river-flood maps: cited depth–damage curve, tile naming, score shape, and reading across tile edges."""
import numpy as np
import pytest
from shapely.geometry import box

from ml.scoring import flood_jrc
from ml.scoring.flood_jrc import TileSet, damage_fraction, flood_score, nominal_tile_name, tile_name


def test_depth_damage_is_the_cited_huizinga_curve():
    assert damage_fraction(0.0) == 0.0 and damage_fraction(0.5) == 0.25 and damage_fraction(2.0) == 0.6
    assert damage_fraction(6.0) == 1.0 and damage_fraction(9.0) == 1.0
    assert abs(damage_fraction(0.25) - 0.125) < 1e-9          # linear between points


def test_score_is_floodplain_share_weighted_by_damage():
    assert flood_score(1.0, 2.0) == 60.0 and flood_score(0.5, 2.0) == 30.0 and flood_score(0.0, 5.0) == 0.0
    assert flood_score(1.0, 0.0) == 0.0                       # inundated share with no depth: nothing to damage


def test_nominal_tile_names_use_the_top_left_corner_and_w0_for_the_zero_column():
    assert nominal_tile_name(45.0, -95.0) == "N50_W100" and nominal_tile_name(48.8, 2.3) == "N50_W0"
    assert nominal_tile_name(51.5, -0.1) == "N60_W10" and nominal_tile_name(-33.9, 151.2) == "S30_E150"


# ── Two synthetic tiles laid out like the published ones: corners shifted off the nominal 10° grid, one pixel grid,
#    edges meeting exactly. West tile dry, east tile flooded 2 m, a permanent-water strip on the east tile.
RES, SHIFT_X, SHIFT_Y = 0.05, -0.03, 0.01
TILES = {"N10_W0": 0.0, "N10_E10": 10.0}                     # name → nominal left edge


def _write(path, left, data, nodata):
    import rasterio
    from rasterio.transform import from_origin
    with rasterio.open(path, "w", driver="GTiff", height=data.shape[0], width=data.shape[1], count=1, dtype=data.dtype,
                       crs="EPSG:4326", transform=from_origin(left + SHIFT_X, 10.0 + SHIFT_Y, RES, RES), nodata=nodata) as ds:
        ds.write(data, 1)


@pytest.fixture
def synthetic_tiles(tmp_path, monkeypatch):
    n = int(round(10.0 / RES))
    ids = {name: i for i, name in enumerate(TILES, start=1)}
    for name, left in TILES.items():
        depth = np.full((n, n), -9999.0, dtype="float32") if name == "N10_W0" else np.full((n, n), 2.0, dtype="float32")
        for rp in flood_jrc.RETURN_PERIODS:
            _write(tmp_path / f"ID{ids[name]}_{name}_RP{rp}_depth.tif", left, depth, -9999.0)
        water = np.full((n, n), 255, dtype="uint8")
        if name == "N10_E10":
            water[:, 2] = 1                                   # a river channel two pixels in from the west edge
        _write(tmp_path / f"ID{ids[name]}_{name}_permanent_water.tif", left, water, 255)
    monkeypatch.setattr(flood_jrc, "TILE_DIR", str(tmp_path))
    monkeypatch.setattr(flood_jrc, "_tiles", lambda: ids)
    flood_jrc.tile_bounds.cache_clear()
    yield
    flood_jrc.tile_bounds.cache_clear()


def test_point_is_assigned_by_the_tiles_real_extent(synthetic_tiles):
    edge = 10.0 + SHIFT_X                                     # the real west edge of the east tile: 9.97
    assert nominal_tile_name(5.0, 9.99) == "N10_W0"           # the nominal grid says west …
    assert tile_name(5.0, 9.99) == "N10_E10"                  # … but the point lies on the east tile
    assert tile_name(5.0, edge - 0.01) == "N10_W0"
    assert tile_name(5.0, 25.0) is None                       # off every tile


def test_cell_straddling_an_edge_is_summed_across_both_tiles(synthetic_tiles):
    edge = 10.0 + SHIFT_X
    ts = TileSet()
    try:
        # 4 px wide: 2 px on the dry west tile, 2 px on the flooded east tile (neither is the water column)
        st = ts.stats(box(edge - 2 * RES, 5.0, edge + 2 * RES, 5.0 + 2 * RES))
        assert st[100][0] == pytest.approx(0.5) and st[100][1] == pytest.approx(2.0)
        # wholly on the west tile, just inside its edge: dry land, not "no data"
        assert ts.stats(box(edge - 2 * RES, 5.0, edge - 0.001, 5.0 + 2 * RES))[100][0] == 0.0
        # across the edge into the water column: the river channel is neither land nor flooded land
        st = ts.stats(box(edge, 5.0, edge + 3 * RES, 5.0 + 2 * RES))
        assert st[100][0] == pytest.approx(1.0)               # 2 flooded px of 2 land px; the water column is excluded
    finally:
        ts.close()


def test_a_cell_is_not_scored_from_a_partial_read(synthetic_tiles, tmp_path):
    (tmp_path / "ID2_N10_E10_RP500_depth.tif").unlink()     # east tile incomplete
    ts = TileSet()
    try:
        straddle = box(9.9, 5.0, 10.05, 5.1)
        assert not ts.readable(straddle) and ts.stats(straddle) is None
        assert ts.readable(box(5.0, 5.0, 5.1, 5.1))           # the complete west tile still reads
    finally:
        ts.close()
