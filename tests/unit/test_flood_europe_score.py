"""The flood score on the JRC European maps inside the countries they cover (the product owner's decision of
2026-10-21): the place decides the maps, the European maps give the same statistic as the global tiles, and where they
do not reach a place the global maps serve — as the loss engine reads the two."""
import numpy as np
import pytest
from shapely.geometry import box

from ml.scoring import flood_jrc
from ml.scoring.flood_jrc import EUROPE_MODEL_VERSION, FLOOD_MODEL_VERSION, EuropeMaps, read_polygon

rasterio = pytest.importorskip("rasterio")


class _Maps:
    def __init__(self, st):
        self.st = st

    def stats(self, polygon):
        return self.st

    def readable(self, polygon):
        return self.st is not None

    def close(self):
        pass


EU, GLOBAL = {100: (0.5, 1.0, 1.0)}, {100: (0.2, 0.5, 0.5)}


def test_a_covered_country_reads_the_european_maps_and_any_other_place_the_global_maps():
    assert read_polygon(box(0, 0, 1, 1), "DE", tiles=_Maps(GLOBAL), europe=_Maps(EU)) == (EUROPE_MODEL_VERSION, EU)
    assert read_polygon(box(0, 0, 1, 1), "US", tiles=_Maps(GLOBAL), europe=_Maps(EU)) == (FLOOD_MODEL_VERSION, GLOBAL)
    assert read_polygon(box(0, 0, 1, 1), "RU", tiles=_Maps(GLOBAL), europe=_Maps(EU)) == (FLOOD_MODEL_VERSION, GLOBAL)
    assert read_polygon(box(0, 0, 1, 1), None, tiles=_Maps(GLOBAL), europe=_Maps(EU)) == (FLOOD_MODEL_VERSION, GLOBAL)


def test_where_the_european_maps_do_not_reach_the_global_maps_serve():
    assert read_polygon(box(0, 0, 1, 1), "DE", tiles=_Maps(GLOBAL), europe=_Maps(None)) == (FLOOD_MODEL_VERSION, GLOBAL)


def test_a_layer_not_in_use_serves_no_place(monkeypatch):
    from services.loss import registry
    real = registry.layer
    monkeypatch.setattr(registry, "layer", lambda k: {**real(k), "status": "candidate"} if k == flood_jrc.EUROPE_LAYER else real(k))
    assert not flood_jrc.europe_serves("DE")


def test_a_cell_on_a_coast_takes_the_one_country_its_corners_fall_in(monkeypatch):
    import h3

    from services.geo import cells
    cell = h3.latlng_to_cell(52.37, 4.89, 8)
    centre = h3.cell_to_latlng(cell)
    monkeypatch.setattr(cells, "country_of", lambda la, lo: None if (la, lo) == centre else "NL")
    assert flood_jrc.cell_country(cell) == "NL"
    corners = {xy: ("NL" if i % 2 else "BE") for i, xy in enumerate(h3.cell_to_boundary(cell))}
    monkeypatch.setattr(cells, "country_of", lambda la, lo: corners.get((la, lo)))
    assert flood_jrc.cell_country(cell) is None                 # corners in two countries: none is chosen


def test_the_european_maps_give_the_tiles_statistic(tmp_path, monkeypatch):
    from rasterio.transform import from_origin
    monkeypatch.setenv("RASTER_SAMPLER_INPROCESS", "1")
    n, res = 40, 0.05

    def write(name, data, nodata):
        with rasterio.open(tmp_path / name, "w", driver="GTiff", height=n, width=n, count=1, dtype=data.dtype,
                           crs="EPSG:4326", transform=from_origin(0.0, 2.0, res, res), nodata=nodata) as ds:
            ds.write(data, 1)
        return str(tmp_path / name)
    depth = np.full((n, n), -9999.0, dtype="float32")
    depth[:, 20:] = 2.0                                          # east half flooded 2 m, west half dry
    depth[:, 25] = 0.04                                          # raster noise: dry
    water = np.full((n, n), -9999.0, dtype="float64")
    water[:, 30] = 1                                             # a river channel: neither land nor flooded
    eu = EuropeMaps.__new__(EuropeMaps)
    eu.paths = {rp: write(f"RP{rp}.tif", depth, -9999.0) for rp in flood_jrc.RETURN_PERIODS}
    eu.water = write("water.tif", water, -9999.0)
    st = eu.stats(box(0.9, 0.5, 1.7, 1.0))                       # columns 18–33 (16 wide): 2 dry, 13 land east, 1 water
    assert st[100][0] == pytest.approx(12 / 15)                  # 12 wet of 15 land columns (noise column dry)
    assert st[100][1] == pytest.approx(2.0)
    assert eu.stats(box(5.0, 5.0, 6.0, 6.0)) is None             # off the maps: not a dry place
