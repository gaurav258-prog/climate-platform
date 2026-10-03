"""Fetch global ERA5-Land monthly means (Supply outlook foundation, phase 2) — the same product and variables as the
regional baselines the crop calibrations use today (scripts/fetch_era5_baseline.py: total precipitation, 2 m
temperature, potential evaporation), for the whole globe at 0.1°, one year per request, so a run can be resumed and a
year that already landed is not fetched again.

  data/datasets/era5_land_monthly/era5land_monthly_<year>.nc        (git-ignored)

After the download, --record writes each file's size and sha-256 into data/reference/supply_datasets.json (kept
separate so a long download never writes a tracked file while other work runs).

Source: Copernicus Climate Change Service (C3S) Climate Data Store, ERA5-Land monthly averaged data (Muñoz Sabater, J.,
2019), doi:10.24381/cds.68d2bb30 — licence: Copernicus licence (attribution: "Contains modified Copernicus Climate
Change Service information <year>").

    python -m scripts.fetch_era5_land_global                 # 1991-2024, resumes
    python -m scripts.fetch_era5_land_global --record        # pin the landed files in the manifest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "datasets" / "era5_land_monthly"
MANIFEST = ROOT / "data" / "reference" / "supply_datasets.json"
VARIABLES = ["total_precipitation", "2m_temperature", "potential_evaporation"]
YEARS = range(1991, 2025)


def _path(year: int) -> Path:
    return OUT / f"era5land_monthly_{year}.nc"


def fetch_year(client, year: int) -> Path:
    out = _path(year)
    if out.exists() and out.stat().st_size > 0:
        return out
    tmp = out.with_suffix(".part")
    client.retrieve("reanalysis-era5-land-monthly-means", {
        "product_type": ["monthly_averaged_reanalysis"], "variable": VARIABLES, "year": [str(year)],
        "month": [f"{m:02d}" for m in range(1, 13)], "time": ["00:00"],
        "data_format": "netcdf", "download_format": "unarchived"}, str(tmp))
    if zipfile.is_zipfile(tmp):                     # CDS sometimes zips a NetCDF requested unarchived
        with zipfile.ZipFile(tmp) as zf:
            nc = [n for n in zf.namelist() if n.endswith(".nc")]
            if len(nc) != 1:
                raise SystemExit(f"{year}: the archive holds {nc} — expected one NetCDF")
            with zf.open(nc[0]) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
        tmp.unlink()
    else:
        tmp.replace(out)
    return out


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def record() -> None:
    files = [p for p in (_path(y) for y in YEARS) if p.exists()]
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    manifest["era5_land_monthly_global"] = {
        "source": "Copernicus C3S Climate Data Store — ERA5-Land monthly averaged data from 1950 to present "
                  "(Muñoz Sabater 2019), doi:10.24381/cds.68d2bb30; variables: " + ", ".join(VARIABLES),
        "licence": "Copernicus licence",
        "attribution": "Contains modified Copernicus Climate Change Service information 2026",
        "version": "CDS reanalysis-era5-land-monthly-means, monthly_averaged_reanalysis, global 0.1°",
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "path": str(OUT.relative_to(ROOT)), "years": [YEARS.start, YEARS.stop - 1],
        "complete": len(files) == len(YEARS),
        "files": [{"file": p.name, "bytes": p.stat().st_size, "sha256": _sha256(p)} for p in files]}
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")
    print(f"recorded {len(files)}/{len(YEARS)} years, {sum(p.stat().st_size for p in files) / 1e9:.2f} GB")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true")
    a = ap.parse_args()
    if a.record:
        record()
        return 0
    import cdsapi

    from core.config import settings
    OUT.mkdir(parents=True, exist_ok=True)
    client = cdsapi.Client(url=settings.CDSAPI_URL, key=settings.CDSAPI_KEY or None, quiet=True)   # else ~/.cdsapirc
    total = 0
    for y in YEARS:
        t0 = time.time()
        p = fetch_year(client, y)
        total += p.stat().st_size
        print(f"{y}: {p.stat().st_size / 1e6:.0f} MB in {time.time() - t0:.0f}s · total {total / 1e9:.2f} GB", flush=True)
    print("done — run with --record to pin the files")
    return 0


if __name__ == "__main__":
    os.chdir(ROOT)
    sys.exit(main())
