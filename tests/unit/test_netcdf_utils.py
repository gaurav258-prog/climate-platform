"""
Tests for the NetCDF → H3 regridding utility.
Uses synthetic xarray datasets — no CDS credentials required.
"""
import numpy as np
import pandas as pd
import pytest
import xarray as xr

from core.netcdf_utils import xarray_to_h3_dataframe


def make_synthetic_dataset(
    lats=(43.0, 43.1, 43.2),
    lons=(6.0, 6.1, 6.2),
    times=("2024-07-25T00:00", "2024-07-25T06:00"),
    variable="t2m",
    base_value=300.0,
) -> xr.Dataset:
    """Create a minimal ERA5-like NetCDF dataset for testing."""
    data = np.random.uniform(base_value, base_value + 5, (len(times), len(lats), len(lons)))
    return xr.Dataset(
        {variable: (["time", "latitude", "longitude"], data)},
        coords={
            "time": pd.to_datetime(times),
            "latitude": list(lats),
            "longitude": list(lons),
        },
    )


def test_output_columns():
    ds = make_synthetic_dataset()
    df = xarray_to_h3_dataframe(ds, "t2m")
    assert set(df.columns) == {"h3_cell", "observed_at", "value"}


def test_h3_cells_are_valid_strings():
    ds = make_synthetic_dataset()
    df = xarray_to_h3_dataframe(ds, "t2m")
    assert all(isinstance(c, str) and len(c) == 15 for c in df["h3_cell"])


def test_timestamps_match_input_times():
    times = ("2024-07-25T00:00", "2024-07-25T06:00")
    ds = make_synthetic_dataset(times=times)
    df = xarray_to_h3_dataframe(ds, "t2m")
    unique_times = sorted(df["observed_at"].unique())
    assert len(unique_times) == 2


def test_nan_values_are_dropped():
    lats = (43.0, 43.1)
    lons = (6.0, 6.1)
    data = np.array([[[1.0, np.nan], [np.nan, 2.0]]])  # shape: (1, 2, 2)
    ds = xr.Dataset(
        {"t2m": (["time", "latitude", "longitude"], data)},
        coords={
            "time": pd.to_datetime(["2024-07-25T00:00"]),
            "latitude": list(lats),
            "longitude": list(lons),
        },
    )
    df = xarray_to_h3_dataframe(ds, "t2m")
    assert df["value"].notna().all()


def test_multiple_grid_points_per_h3_cell_are_aggregated():
    # Put 4 closely-spaced lat/lon points that all fall in the same H3 res-8 cell
    tiny_offset = 0.001
    lats = (43.0, 43.0 + tiny_offset)
    lons = (6.0, 6.0 + tiny_offset)
    data = np.array([[[10.0, 20.0], [30.0, 40.0]]])  # shape: (1, 2, 2) → mean = 25.0
    ds = xr.Dataset(
        {"t2m": (["time", "latitude", "longitude"], data)},
        coords={
            "time": pd.to_datetime(["2024-07-25T00:00"]),
            "latitude": list(lats),
            "longitude": list(lons),
        },
    )
    df = xarray_to_h3_dataframe(ds, "t2m")
    # All 4 points should be in one H3 cell, aggregated to their mean
    assert len(df) == 1
    assert df["value"].iloc[0] == pytest.approx(25.0)


def test_empty_dataset_returns_empty_dataframe():
    ds = xr.Dataset(
        {"t2m": (["time", "latitude", "longitude"], np.full((1, 2, 2), np.nan))},
        coords={
            "time": pd.to_datetime(["2024-07-25T00:00"]),
            "latitude": [43.0, 43.1],
            "longitude": [6.0, 6.1],
        },
    )
    df = xarray_to_h3_dataframe(ds, "t2m")
    assert df.empty
