"""Forest-loss layer — the EUDR deforestation truth, read per plot (Hansen GFC).

EUDR forbids sourcing from land deforested AFTER 31 Dec 2020. The authoritative open global
signal is the Hansen Global Forest Change `lossyear` raster (University of Maryland): 1 arc-second
(~30 m), global, one band where 0 = no loss and 1..N = the year of tree-cover loss (year 2000+N).
A plot is deforestation-suspect if any pixel inside it lost tree cover in 2021 or later.

We do NOT bulk-download the ~120 MB/tile global set. GDAL reads the tiles over HTTP with range
requests (`/vsicurl/`), so we window-read only the pixels under one plot polygon — the same
"golden source stays remote, compute per asset on demand" pattern the platform already uses for
ERA5. A tile can also be pre-staged into `data/forest/` (scripts/ingest_forest_baseline.py) for
offline / faster reads; the local copy is used automatically when present.

Scope: the signal is tree-cover LOSS since the cutoff, masked by `treecover2000` so loss is only
counted on land that was forest at baseline (the `min_treecover_pct` threshold; `forest_pixels`
records the masked footprint). It does not distinguish deforestation from managed-plantation
harvest — so the output is `loss` (evidence to review), not a final legal "non-compliant" verdict;
the Phase-1 determination layer applies the EUDR rule on top.
"""
from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass
from typing import Optional

import rasterio
from rasterio.mask import mask as rio_mask
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry

# Pin the dataset version — provenance requires an exact, citable source.
GFC_VERSION = "GFC-2024-v1.12"
GFC_BASE = f"https://storage.googleapis.com/earthenginepartners-hansen/{GFC_VERSION}"
EUDR_CUTOFF_YEAR = 2020            # loss in 2021+ (lossyear >= 21) is EUDR-relevant
MIN_TREECOVER_PCT = 10             # FAO-aligned "forest": >=10% canopy in 2000 (treecover2000 band)
STAGE_DIR = "data/forest"
# Read-a-point plots need a footprint; buffer the point to a small disc to sample pixels.
DEFAULT_POINT_BUFFER_M = 100.0

_GDAL_ENV = dict(
    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
    GDAL_HTTP_MULTIRANGE="YES",
    VSI_CACHE="TRUE",
)


@dataclass
class ForestLoss:
    has_loss: bool                 # any post-cutoff loss ON FOREST inside the plot?
    loss_pixels: int               # count of post-cutoff loss pixels (on forest)
    total_pixels: int              # pixels sampled inside the plot
    loss_ha: float                 # approx hectares of forest lost (per-pixel area at latitude)
    loss_fraction: float           # loss_pixels / total_pixels
    first_loss_year: Optional[int] # earliest post-cutoff forest-loss year (e.g. 2022)
    tile: str                      # tile id used, for provenance
    cutoff_year: int
    source: str                    # dataset version + read mode
    insufficient: bool             # True when no pixels could be read (off-grid / no data)
    min_treecover_pct: int = MIN_TREECOVER_PCT   # forest threshold applied (0 = no mask)
    forest_pixels: int = 0         # pixels that were forest in 2000 (treecover >= threshold)

    def as_evidence(self) -> dict:
        return asdict(self)


def tile_id(lat: float, lon: float) -> str:
    """Hansen 10x10 degree tile id for a coordinate, e.g. (6.7,-1.6) -> '10N_010W'.

    Tiles are named by their TOP-LEFT corner: top-latitude = ceil(lat/10)*10, left-longitude =
    floor(lon/10)*10."""
    top = int(math.ceil(lat / 10.0) * 10)
    left = int(math.floor(lon / 10.0) * 10)
    lat_s = f"{abs(top):02d}{'N' if top >= 0 else 'S'}"
    lon_s = f"{abs(left):03d}{'E' if left >= 0 else 'W'}"
    return f"{lat_s}_{lon_s}"


def tile_source(tid: str, band: str = "lossyear", stage_dir: str = STAGE_DIR) -> str:
    """Local staged path if it exists, else the remote /vsicurl URL for the tile."""
    fname = f"Hansen_{GFC_VERSION}_{band}_{tid}.tif"
    local = os.path.join(stage_dir, fname)
    if os.path.exists(local):
        return local
    return f"/vsicurl/{GFC_BASE}/{fname}"


def _pixel_area_ha(transform, lat: float) -> float:
    """Approx ground area of one pixel (deg x deg) at latitude `lat`, in hectares."""
    px_deg = abs(transform.a)          # ~0.00025 deg (1 arc-second)
    py_deg = abs(transform.e)
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat))
    return (px_deg * m_per_deg_lon) * (py_deg * m_per_deg_lat) / 10_000.0


def _read_band(src: str, footprint) -> tuple:
    with rasterio.Env(**_GDAL_ENV):
        with rasterio.open(src) as ds:
            arr, transform = rio_mask(ds, [mapping(footprint)], crop=True, filled=True, nodata=0)
    return arr[0], transform


def forest_loss_since(geom: BaseGeometry, cutoff_year: int = EUDR_CUTOFF_YEAR,
                      min_treecover_pct: int = MIN_TREECOVER_PCT, stage_dir: str = STAGE_DIR,
                      point_buffer_m: float = DEFAULT_POINT_BUFFER_M) -> ForestLoss:
    """Post-cutoff FOREST loss inside a plot geometry (shapely Point or Polygon).

    Reads the Hansen lossyear tile covering the plot centroid, masks to the plot footprint, and
    counts pixels whose loss year is after `cutoff_year` AND that were forest in 2000
    (treecover2000 >= `min_treecover_pct`, FAO-aligned). Masking by treecover is what turns raw
    tree-cover loss into a DEFORESTATION signal — so pruning an olive grove or harvesting a
    plantation that was never forest is not flagged. Set min_treecover_pct=0 to skip the mask.
    A Point is buffered to a small disc. Cross-tile plots use the centroid tile in v0."""
    c = geom.centroid
    lat, lon = c.y, c.x
    tid = tile_id(lat, lon)
    src = tile_source(tid, "lossyear", stage_dir)
    mode = "remote" if src.startswith("/vsicurl/") else "staged"

    footprint = geom
    if geom.geom_type == "Point":
        deg = point_buffer_m / (111_320.0 * max(math.cos(math.radians(lat)), 1e-6))
        footprint = geom.buffer(deg)

    loss_year_min = (cutoff_year - 2000) + 1     # 2020 -> 21 (i.e. 2021)
    try:
        loss_band, transform = _read_band(src, footprint)
        total = int(loss_band.size)
        if total == 0:
            raise ValueError("no pixels under plot footprint")
        loss_mask = loss_band >= loss_year_min

        forest_pixels = total
        if min_treecover_pct > 0:
            tc_band, _ = _read_band(tile_source(tid, "treecover2000", stage_dir), footprint)
            forest_mask = tc_band >= min_treecover_pct
            forest_pixels = int(forest_mask.sum())
            loss_mask = loss_mask & forest_mask   # deforestation = loss ON land that was forest

        loss_pixels = int(loss_mask.sum())
        years = loss_band[loss_mask]
        first = 2000 + int(years.min()) if loss_pixels else None
        loss_ha = round(loss_pixels * _pixel_area_ha(transform, lat), 4)
        return ForestLoss(
            has_loss=loss_pixels > 0, loss_pixels=loss_pixels, total_pixels=total,
            loss_ha=loss_ha, loss_fraction=round(loss_pixels / total, 4), first_loss_year=first,
            tile=tid, cutoff_year=cutoff_year, source=f"{GFC_VERSION} ({mode})", insufficient=False,
            min_treecover_pct=min_treecover_pct, forest_pixels=forest_pixels)
    except Exception as e:
        # Never fabricate a determination on a read failure — surface it as insufficient.
        return ForestLoss(False, 0, 0, 0.0, 0.0, None, tid, cutoff_year,
                          f"{GFC_VERSION} read-error: {e}", insufficient=True,
                          min_treecover_pct=min_treecover_pct)
