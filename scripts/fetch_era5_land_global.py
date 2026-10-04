"""Fetch global ERA5-Land monthly means (Supply outlook foundation, phase 2) — the same product and variables as the
regional baselines the crop calibrations use today (scripts/fetch_era5_baseline.py: total precipitation, 2 m
temperature, potential evaporation), for the whole globe at 0.1°. The CDS queues each request (~50 min per request on 2026-10-04) and rejects more than a
few queued requests per dataset ("Number queued requests for this dataset is temporarily limited"), so requests are
sent one at a time and each asks for several years (--years-per-request, default 6): a run resumes, and a year a file
already holds is never fetched again.

  data/datasets/era5_land_monthly/era5land_monthly_<year>.nc  or  era5land_monthly_<first>-<last>.nc   (git-ignored)

After the download, --record writes each file's size and sha-256 into data/reference/supply_datasets.json (kept
separate so a long download never writes a tracked file while other work runs).

Source: Copernicus Climate Change Service (C3S) Climate Data Store, ERA5-Land monthly averaged data (Muñoz Sabater, J.,
2019), doi:10.24381/cds.68d2bb30 — licence: Copernicus licence (attribution: "Contains modified Copernicus Climate
Change Service information <year>").

    python -m scripts.fetch_era5_land_global                 # 1991-2024, resumes, six years per request
    python -m scripts.fetch_era5_land_global --record        # pin the landed files in the manifest
"""
from __future__ import annotations

import argparse
import hashlib
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


def _path(first: int, last: int) -> Path:
    return OUT / (f"era5land_monthly_{first}.nc" if first == last else f"era5land_monthly_{first}-{last}.nc")


def _files() -> dict[Path, range]:
    """{file: the years it holds} for every landed file (the years are in its name)."""
    out = {}
    for p in sorted(OUT.glob("era5land_monthly_*.nc")):
        span = p.stem.removeprefix("era5land_monthly_").split("-")
        if p.stat().st_size > 0 and all(x.isdigit() for x in span):
            out[p] = range(int(span[0]), int(span[-1]) + 1)
    return out


def _requests(per_request: int) -> list[list[int]]:
    """The years no file holds, in runs of consecutive years of at most per_request."""
    held = {y for years in _files().values() for y in years}
    runs: list[list[int]] = []
    for y in (y for y in YEARS if y not in held):
        if runs and runs[-1][-1] == y - 1 and len(runs[-1]) < per_request:
            runs[-1].append(y)
        else:
            runs.append([y])
    return runs


def fetch_years(client, years: list[int]) -> Path:
    out = _path(years[0], years[-1])
    tmp = out.with_suffix(".part")
    client.retrieve("reanalysis-era5-land-monthly-means", {
        "product_type": ["monthly_averaged_reanalysis"], "variable": VARIABLES, "year": [str(y) for y in years],
        "month": [f"{m:02d}" for m in range(1, 13)], "time": ["00:00"],
        "data_format": "netcdf", "download_format": "unarchived"}, str(tmp))
    if zipfile.is_zipfile(tmp):                     # CDS sometimes zips a NetCDF requested unarchived
        with zipfile.ZipFile(tmp) as zf:
            nc = [n for n in zf.namelist() if n.endswith(".nc")]
            if len(nc) != 1:
                raise SystemExit(f"{years}: the archive holds {nc} — expected one NetCDF")
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
    from scripts.fetch_supply_datasets import record as record_entry
    held = _files()
    files = list(held)
    record_entry("era5_land_monthly_global", {
        "source": "Copernicus C3S Climate Data Store — ERA5-Land monthly averaged data from 1950 to present "
                  "(Muñoz Sabater 2019), doi:10.24381/cds.68d2bb30; variables: " + ", ".join(VARIABLES),
        "licence": "Copernicus licence",
        "attribution": "Contains modified Copernicus Climate Change Service information 2026",
        "version": "CDS reanalysis-era5-land-monthly-means, monthly_averaged_reanalysis, global 0.1°",
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "path": str(OUT.relative_to(ROOT)), "years": [YEARS.start, YEARS.stop - 1],
        "complete": {y for years in held.values() for y in years} >= set(YEARS),
        "files": [{"file": p.name, "bytes": p.stat().st_size, "sha256": _sha256(p)} for p in files]})
    print(f"recorded {len(files)} files, {sum(len(v) for v in held.values())}/{len(YEARS)} years, "
          f"{sum(p.stat().st_size for p in files) / 1e9:.2f} GB")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--years-per-request", type=int, default=6)
    a = ap.parse_args()
    if a.record:
        record()
        return 0
    import cdsapi

    from core.config import settings
    OUT.mkdir(parents=True, exist_ok=True)
    client = cdsapi.Client(url=settings.CDSAPI_URL, key=settings.CDSAPI_KEY or None, quiet=True)   # else ~/.cdsapirc
    total = 0
    for years in _requests(a.years_per_request):
        t0 = time.time()
        p = fetch_years(client, years)
        total += p.stat().st_size
        print(f"{years[0]}-{years[-1]}: {p.stat().st_size / 1e6:.0f} MB in {time.time() - t0:.0f}s · "
              f"total {total / 1e9:.2f} GB", flush=True)
    print("done — run with --record to pin the files")
    return 0


if __name__ == "__main__":
    os.chdir(ROOT)
    sys.exit(main())
