"""E167: a season's figure only when every season month has one — never a mean or minimum over part of a season."""
import numpy as np
import pandas as pd
import xarray as xr

from ml.features import frost, soil_moisture
from ml.features.drought import season_mean, seasonal_by_year


def test_season_mean_needs_every_month():
    assert season_mean([1.0, 2.0, 3.0], 3, 2) == 2.0
    assert season_mean([np.nan, 2.0, 3.0], 3, 2) is None      # a month without its accumulation window
    assert season_mean([2.0, 3.0], 3, 2) is None               # a season still in progress at the record's end


def _monthly(start: str, n: int, first_nan: int = 0) -> xr.Dataset:
    t = pd.date_range(start, periods=n, freq="MS")
    v = np.arange(n, dtype=float)
    v[:first_nan] = np.nan
    a = xr.DataArray(v[:, None, None], dims=("time", "latitude", "longitude"),
                     coords={"time": t, "latitude": [0.0], "longitude": [0.0]})
    return xr.Dataset({"spei": a, "spi": a, "temp_anom_c": a + 100, "precip_deficit_mm": a})


def test_the_first_season_without_its_window_has_no_spei():
    """SPEI-6 for April 1991 needs Nov 1990: an Apr–Aug season in 1991 has no SPEI, 1992's has."""
    rows = {r["year"]: r for r in seasonal_by_year(_monthly("1991-01", 24, first_nan=5), [4, 5, 6, 7, 8])}
    assert rows[1991]["spei"] is None
    assert rows[1992]["spei"] == season_mean(np.arange(15, 20, dtype=float), 5, 2)


def test_a_season_in_progress_has_no_figure():
    rows = {r["year"]: r for r in seasonal_by_year(_monthly("1991-01", 18), [4, 5, 6, 7, 8])}   # ends June 1992
    assert rows[1991]["spei"] is not None and rows[1992]["spei"] is None


def test_soil_water_follows_the_same_rule():
    sm = _monthly("1991-01", 18)["spei"]
    rows = {r["year"]: r["sm_z"] for r in soil_moisture.seasonal_by_year(sm, [4, 5, 6, 7, 8])}
    assert rows[1991] is not None and rows[1992] is None


def _hourly(start: str, end: str) -> xr.Dataset:
    t = pd.date_range(start, end, freq="6h")
    a = xr.DataArray(np.full((len(t), 1, 1), 5.0), dims=("time", "latitude", "longitude"),
                     coords={"time": t, "latitude": [0.0], "longitude": [0.0]})
    return xr.Dataset({"T": a})


def test_frost_season_minimum_needs_every_month():
    full = frost.seasonal_by_year(_hourly("2020-05-01", "2020-09-30 18:00"), [5, 6, 7, 8, 9])
    part = frost.seasonal_by_year(_hourly("2021-05-01", "2021-07-15"), [5, 6, 7, 8, 9])
    assert full[0]["season_min_tmin_c"] == 5.0
    assert part[0]["season_min_tmin_c"] is None
    assert frost.to_h3_frame(_hourly("2021-05-01", "2021-07-15"), 2021, [5, 6, 7, 8, 9]).empty
