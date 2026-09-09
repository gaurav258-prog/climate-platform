"""Raster reads happen in a child process: a hard crash or a hang there returns None here and the child is replaced."""
import os

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")


@pytest.fixture(scope="module")
def tif(tmp_path_factory):
    from rasterio.transform import from_origin
    p = tmp_path_factory.mktemp("r") / "t.tif"
    data = np.arange(100, dtype="float32").reshape(10, 10)          # value = row*10 + col
    with rasterio.open(p, "w", driver="GTiff", height=10, width=10, count=1, dtype="float32", crs="EPSG:4326",
                       transform=from_origin(0.0, 10.0, 1.0, 1.0), nodata=-1.0) as dst:
        dst.write(data, 1)
    return str(p)


@pytest.fixture
def isolated(monkeypatch):
    monkeypatch.delenv("RASTER_SAMPLER_INPROCESS", raising=False)


def test_reads_go_through_the_child_and_match_rasterio(tif, isolated):
    from services.geo import raster_sampler as rs
    meta = rs.info(tif)
    assert meta["bounds"] == [0.0, 0.0, 10.0, 10.0] and meta["nodata"] == -1.0 and "4326" in meta["crs"]
    got = rs.sample(tif, [(2.5, 7.5), (9.5, 0.5)])                 # (x=2.5,y=7.5) → row 2, col 2 → 22
    assert got == [[22.0], [99.0]]                                 # (9.5, 0.5) → row 9, col 9
    w = rs.window(tif, 5.5, 5.5, band=1, half=1)
    assert w.shape == (3, 3) and w[1, 1] == 45.0
    assert rs.health()["alive"] and not rs.health()["inprocess"]


def test_a_dead_child_never_reaches_the_caller_and_is_replaced(tif, isolated):
    from services.geo import raster_sampler as rs
    before = rs.health()["deaths"]
    rs.crash_for_test()                                             # os._exit inside the child
    assert rs.health()["deaths"] == before + 1
    assert rs.sample(tif, [(2.5, 7.5)]) == [[22.0]]                 # respawned transparently
    assert rs.health()["alive"]


def test_missing_file_and_bad_read_are_none_not_exceptions(tif, isolated):
    from services.geo import raster_sampler as rs
    assert rs.info("/nowhere/none.tif") is None
    assert rs.sample(tif, [(50.0, 50.0)]) is not None               # outside → rasterio returns nodata-ish, no crash
    assert rs.window("/nowhere/none.tif", 1, 1) is None


def test_inprocess_mode_for_tests(tif, monkeypatch):
    monkeypatch.setenv("RASTER_SAMPLER_INPROCESS", "1")
    from services.geo import raster_sampler as rs
    assert rs.sample(tif, [(2.5, 7.5)]) == [[22.0]] and rs.health()["inprocess"]
    assert os.environ["RASTER_SAMPLER_INPROCESS"] == "1"
