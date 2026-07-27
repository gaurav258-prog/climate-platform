"""Forest-loss layer (services/intelligence/forest.py) — validated on a synthetic Hansen tile.

No network: we write a tiny GeoTIFF named exactly like the Hansen lossyear tile for the test
location, stage it, and assert the per-plot read finds post-cutoff loss where we planted it and
nothing where we didn't. Pins the EUDR rule (loss in 2021+ counts, 2019 does not) and the
honest insufficient-data path.
"""
import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin
from shapely.geometry import Polygon, Point

from services.intelligence.forest import forest_loss_since, tile_id, GFC_VERSION

# Test location in the Ghana cocoa belt → Hansen tile "10N_010W".
WEST, NORTH, PX = -1.65, 6.75, 0.00025
LOSS_YEAR = 22  # 2022, i.e. after the 2020 cutoff


def _write(path, arr):
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1,
                       dtype="uint8", crs="EPSG:4326", transform=from_origin(WEST, NORTH, PX, PX)) as ds:
        ds.write(arr, 1)


@pytest.fixture
def staged_tile(tmp_path):
    """Write synthetic lossyear + treecover2000 tiles for tile 10N_010W."""
    assert tile_id(6.70, -1.60) == "10N_010W"
    loss = np.zeros((300, 300), dtype=np.uint8)
    loss[80:180, 80:180] = LOSS_YEAR                # 2022 loss ON forest
    loss[200:220, 200:220] = 19                     # 2019 loss (PRE-cutoff, ignored)
    loss[210:240, 60:100] = LOSS_YEAR               # 2022 loss on NON-forest (must be masked out)
    tc = np.full((300, 300), 100, dtype=np.uint8)   # forest everywhere...
    tc[210:240, 60:100] = 0                          # ...except this non-forest block
    _write(tmp_path / f"Hansen_{GFC_VERSION}_lossyear_10N_010W.tif", loss)
    _write(tmp_path / f"Hansen_{GFC_VERSION}_treecover2000_10N_010W.tif", tc)
    return str(tmp_path)


def _rect(col0, col1, row0, row1):
    x0, x1 = WEST + col0 * PX, WEST + col1 * PX
    y1, y0 = NORTH - row0 * PX, NORTH - row1 * PX
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def test_detects_post_cutoff_loss_inside_plot(staged_tile):
    r = forest_loss_since(_rect(90, 170, 90, 170), stage_dir=staged_tile)
    assert not r.insufficient
    assert r.has_loss and r.loss_pixels > 0
    assert r.first_loss_year == 2022
    # ~0.077 ha/pixel at this latitude, so loss_ha tracks loss_pixels sanely.
    assert r.loss_ha == pytest.approx(r.loss_pixels * 0.077, rel=0.15)


def test_clean_plot_has_no_loss(staged_tile):
    r = forest_loss_since(_rect(220, 260, 240, 280), stage_dir=staged_tile)
    assert not r.insufficient
    assert not r.has_loss and r.loss_pixels == 0


def test_pre_cutoff_loss_is_ignored(staged_tile):
    # The 2019 block must NOT count as EUDR loss (cutoff is 2020).
    r = forest_loss_since(_rect(200, 220, 200, 220), stage_dir=staged_tile)
    assert not r.has_loss


def test_loss_on_nonforest_is_masked_out(staged_tile):
    # 2022 loss on land that was NOT forest in 2000 (treecover=0) is not deforestation.
    r = forest_loss_since(_rect(62, 98, 212, 238), stage_dir=staged_tile)
    assert not r.insufficient and not r.has_loss and r.forest_pixels == 0


def test_point_is_buffered_and_sampled(staged_tile):
    # A point inside the 2022 block reads loss via its buffer.
    r = forest_loss_since(Point(WEST + 130 * PX, NORTH - 130 * PX), stage_dir=staged_tile)
    assert r.has_loss and r.total_pixels > 0


def test_missing_tile_is_insufficient_not_fabricated(tmp_path):
    # Mid-Pacific ocean: Hansen publishes no such tile, so it 404s (online) or fails to open
    # (offline) — either way the read is INSUFFICIENT, never a fabricated "no loss". Deterministic
    # regardless of network.
    r = forest_loss_since(Point(-160.0, 0.0), stage_dir=str(tmp_path))
    assert r.insufficient is True and not r.has_loss
