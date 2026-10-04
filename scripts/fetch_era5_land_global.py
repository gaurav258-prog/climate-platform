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

    python -m scripts.fetch_era5_land_global                 # 1991 to last year (six years per request), then
                                                             # this year's months the CDS holds; resumes
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
YEARS = range(1991, datetime.now(timezone.utc).year)     # every full year; the current year's months: fetch_current


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
    full = {y for years in held.values() for y in years} & set(YEARS)
    current = YEARS.stop
    months = held_months(current)
    print(f"recorded {len(files)} files: {len(full)}/{len(YEARS)} full years"
          + (f" + {months} months of {current}" if months else "")
          + f", {sum(p.stat().st_size for p in files) / 1e9:.2f} GB")


def _cds() -> tuple[str, str]:
    """(API url, key) — from the settings, else ~/.cdsapirc (as cdsapi reads them)."""
    from core.config import settings
    url, key = settings.CDSAPI_URL or "https://cds.climate.copernicus.eu/api", settings.CDSAPI_KEY or ""
    rc = Path.home() / ".cdsapirc"
    if not key and rc.exists():
        for line in rc.read_text().splitlines():
            if line.startswith("key:"):
                key = line.split(":", 1)[1].strip()
            elif line.startswith("url:") and not settings.CDSAPI_URL:
                url = line.split(":", 1)[1].strip()
    return url, key


def available_months(year: int) -> list[int]:
    """The months of `year` the CDS holds for these variables — its constraints answer, no download."""
    import requests
    url, key = _cds()
    r = requests.post(f"{url}/retrieve/v1/processes/reanalysis-era5-land-monthly-means/constraints",
                      headers={"PRIVATE-TOKEN": key}, timeout=60,
                      json={"inputs": {"product_type": ["monthly_averaged_reanalysis"], "variable": VARIABLES,
                                       "year": [str(year)]}})
    r.raise_for_status()
    return sorted(int(m) for m in r.json().get("month", []))


def held_months(year: int) -> int:
    """How many months the year's landed file holds (0 when none)."""
    p = _path(year, year)
    if not p.exists():
        return 0
    import xarray as xr
    with xr.open_dataset(p) as ds:
        return int(ds.sizes.get("valid_time", ds.sizes.get("time", 0)))


def fetch_current(client, year: int | None = None) -> Path | None:
    """The current year's months the CDS holds, in one file replaced as months arrive. None when nothing is newer."""
    year = year or datetime.now(timezone.utc).year
    months = available_months(year)
    if not months or len(months) <= held_months(year):
        return None
    out = _path(year, year)
    tmp = out.with_suffix(".part")
    client.retrieve("reanalysis-era5-land-monthly-means", {
        "product_type": ["monthly_averaged_reanalysis"], "variable": VARIABLES, "year": [str(year)],
        "month": [f"{m:02d}" for m in months], "time": ["00:00"],
        "data_format": "netcdf", "download_format": "unarchived"}, str(tmp))
    tmp.replace(out)
    return out


class FetchRunning(RuntimeError):
    pass


def locked():
    """One fetch at a time (the CDS refuses more queued requests per dataset): an exclusive lock on the folder."""
    import contextlib
    import fcntl

    @contextlib.contextmanager
    def _lock():
        OUT.mkdir(parents=True, exist_ok=True)
        with open(OUT / ".fetch.lock", "w") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise FetchRunning("another ERA5-Land fetch is running") from None
            yield
    return _lock()


def fetch_all(years_per_request: int = 6, current: bool = True, log=print) -> list[Path]:
    """The missing full years, then the current year's months — under the lock. Returns the files written."""
    import cdsapi
    url, key = _cds()
    written = []
    with locked():
        client = cdsapi.Client(url=url, key=key or None, quiet=True)
        for years in _requests(years_per_request):
            t0 = time.time()
            p = fetch_years(client, years)
            written.append(p)
            log(f"{years[0]}-{years[-1]}: {p.stat().st_size / 1e6:.0f} MB in {time.time() - t0:.0f}s")
        if current:
            p = fetch_current(client)
            if p is not None:
                written.append(p)
                log(f"{p.name}: {held_months(datetime.now(timezone.utc).year)} months")
    return written


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--years-per-request", type=int, default=6)
    ap.add_argument("--no-current", action="store_true", help="full years only, not the current year's months")
    a = ap.parse_args()
    if a.record:
        record()
        return 0
    try:
        fetch_all(a.years_per_request, current=not a.no_current, log=lambda m: print(m, flush=True))
    except FetchRunning as e:
        print(e)
        return 1
    print("done — run with --record to pin the files")
    return 0


if __name__ == "__main__":
    os.chdir(ROOT)
    sys.exit(main())
