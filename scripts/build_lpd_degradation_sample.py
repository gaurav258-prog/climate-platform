"""Build the independent soil-degradation validation target: a grid sample of the Li et al. (2025) 30 m Land
Productivity Dynamics (LPD) raster over its two downloaded Mediterranean tiles.

Source (open, independent of our model): Li et al. 2025, "A 30-meter resolution global land productivity
dynamics dataset from 2013 to 2022" (Zenodo 10.5281/zenodo.14512248) — built from Landsat-8 + MODIS via the
FAO-WOCAT LPD methodology. NOT the same pipeline as our current model (which reads Trends.Earth SDG 15.3.1,
Zenodo 10.5281/zenodo.17079487, Conservation International). Two Mediterranean-basin tiles were downloaded to
data/degradation_val/: tile_45W_52N (Iberia + France, lon -45..0) and tile_0_52N (Italy/Greece/Balkans/Levant,
lon 0..45), both lat 28..52N, as GDAL sub-tiled chunks of one large raster per geometry cell.

Pixel legend (source paper), band 1, Byte: 0 = no data, 1 = declining LPD, 2 = early signs of decline,
3 = stable but stressed, 4 = stable and not stressed, 5 = increasing LPD (higher = healthier land).

This script mosaics each tile's chunks into a VRT (gdalbuildvrt), lays a regular lon/lat grid across the
combined bounding box, samples the VRT at each node through services/geo/raster_sampler (the platform's
process-isolated raster reader), drops nodata (0) nodes, and writes the survivors to
data/degradation_val/li_lpd_sample.csv (lat, lon, lpd_status). A large candidate grid is used and then
randomly subsampled (fixed seed) to a target count, so the sample is spatially representative rather than
however the raw grid happened to land.

Usage: PYTHONPATH=. .venv/bin/python scripts/build_lpd_degradation_sample.py
"""
from __future__ import annotations

import csv
import random
import subprocess
from pathlib import Path

VAL_DIR = Path("data/degradation_val")
TILES = {
    "tile_45W_52N": VAL_DIR / "tile_45W_52N.vrt",
    "tile_0_52N": VAL_DIR / "tile_0_52N.vrt",
}
OUT_CSV = VAL_DIR / "li_lpd_sample.csv"
GRID_STEP_DEG = 0.1          # ~11 km candidate lattice — fine enough for a representative sample, coarse
                              # enough that the run stays fast; land fraction of the bbox is a small minority
TARGET_N = 4000               # final sample size after subsampling valid (non-nodata) land nodes
SEED = 20260917


def _build_vrt(tile_dir: Path, vrt_path: Path) -> None:
    if vrt_path.exists():
        return
    tifs = sorted(str(p) for p in tile_dir.glob("*.tif"))
    if not tifs:
        raise FileNotFoundError(f"no .tif chunks found in {tile_dir}")
    subprocess.run(["gdalbuildvrt", str(vrt_path), *tifs], check=True, capture_output=True)


def _grid(bounds: tuple[float, float, float, float], step: float) -> list[tuple[float, float]]:
    left, bottom, right, top = bounds
    lons = [left + i * step for i in range(int((right - left) / step) + 1)]
    lats = [bottom + j * step for j in range(int((top - bottom) / step) + 1)]
    return [(lat, lon) for lat in lats for lon in lons]


def main() -> int:
    from services.geo.raster_sampler import info, sample

    for name, vrt in TILES.items():
        _build_vrt(VAL_DIR / name, vrt)

    rows: list[tuple[float, float, int]] = []
    for name, vrt in TILES.items():
        meta = info(str(vrt))
        if meta is None:
            print(f"  ! could not read {vrt}")
            continue
        candidates = _grid(tuple(meta["bounds"]), GRID_STEP_DEG)
        pts = [(lon, lat) for lat, lon in candidates]
        vals = sample(str(vrt), pts, band=1)
        if vals is None:
            print(f"  ! sampling failed for {vrt}")
            continue
        kept = 0
        for (lat, lon), v in zip(candidates, vals):
            status = int(round(v[0]))
            if status < 1 or status > 5:   # 0 = nodata, anything else off-legend
                continue
            rows.append((lat, lon, status))
            kept += 1
        print(f"  {name}: {len(candidates)} candidates, {kept} valid land nodes")

    rng = random.Random(SEED)
    if len(rows) > TARGET_N:
        rows = rng.sample(rows, TARGET_N)

    VAL_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lat", "lon", "lpd_status"])
        w.writerows(sorted(rows))
    print(f"  wrote {len(rows)} points -> {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
