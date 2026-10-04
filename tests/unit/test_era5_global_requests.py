"""E159: the global ERA5-Land download asks the CDS for several years per request, one request at a time (the CDS
rejects more than a few queued requests per dataset), and never asks again for a year a landed file holds."""
from __future__ import annotations

from scripts import fetch_era5_land_global as F


def test_requests_cover_only_missing_years_in_consecutive_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "OUT", tmp_path)
    monkeypatch.setattr(F, "YEARS", range(1991, 2005))
    (tmp_path / "era5land_monthly_1991.nc").write_bytes(b"x")
    (tmp_path / "era5land_monthly_1995-1997.nc").write_bytes(b"x")
    (tmp_path / "era5land_monthly_1998.nc").write_bytes(b"")             # empty: not landed
    (tmp_path / "era5land_monthly_1999.part").write_bytes(b"x")          # unfinished: not landed
    assert F._requests(4) == [[1992, 1993, 1994], [1998, 1999, 2000, 2001], [2002, 2003, 2004]]
    assert F._path(1992, 1994).name == "era5land_monthly_1992-1994.nc" and F._path(2000, 2000).name == "era5land_monthly_2000.nc"
