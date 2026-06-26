"""
Shared utility: convert xarray Datasets (NetCDF) to H3-indexed DataFrames.

ERA5, GloFAS, and Sentinel-3 all arrive as NetCDF. This module handles the
spatial regridding — from lat/lon grids to H3 resolution-8 cells — so each
adapter only needs to know what variables to request, not how to reproject them.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd
import xarray as xr

import h3

from core.config import settings

logger = logging.getLogger(__name__)


def xarray_to_h3_dataframe(
    ds: xr.Dataset,
    variable: str,
    lat_dim: str = "latitude",
    lon_dim: str = "longitude",
    time_dim: Optional[str] = "time",
) -> pd.DataFrame:
    """
    Convert one variable in an xarray Dataset to a DataFrame of H3 observations.

    For each timestamp in the dataset:
    - Assign every (lat, lon) grid point to its H3 resolution-8 cell
    - Aggregate multiple grid points per cell by mean (ERA5 ~0.1° grid → ~0.4° H3 cell)

    Returns DataFrame with columns: h3_cell, observed_at, value
    NaN values are dropped before aggregation.
    """
    da = ds[variable]

    # CDS migrated from 'time' to 'valid_time' in 2024 — auto-detect if needed
    if time_dim is not None and time_dim not in da.dims:
        candidates = [d for d in da.dims if d not in (lat_dim, lon_dim)]
        if candidates:
            time_dim = candidates[0]
            logger.debug(f"[netcdf] time dim not found, using '{time_dim}'")
        else:
            time_dim = None

    # Handle datasets with no time dimension (e.g. static terrain)
    if time_dim is None:
        return _single_timestep_to_df(da, lat_dim, lon_dim, observed_at=None)

    frames = []
    for t in da[time_dim].values:
        snapshot = da.sel({time_dim: t})
        df = _single_timestep_to_df(snapshot, lat_dim, lon_dim, observed_at=pd.Timestamp(t))
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame(columns=["h3_cell", "observed_at", "value"])

    return pd.concat(frames, ignore_index=True)


def _single_timestep_to_df(
    da: xr.DataArray,
    lat_dim: str,
    lon_dim: str,
    observed_at,
) -> pd.DataFrame:
    lats = da[lat_dim].values
    lons = da[lon_dim].values
    values = da.values

    # Flatten 2D grid to 1D
    lat_grid, lon_grid = np.meshgrid(lats, lons, indexing="ij")
    lat_flat = lat_grid.ravel()
    lon_flat = lon_grid.ravel()
    val_flat = values.ravel()

    mask = ~np.isnan(val_flat)
    if not mask.any():
        return pd.DataFrame(columns=["h3_cell", "observed_at", "value"])

    cells = [
        h3.latlng_to_cell(float(lat), float(lon), settings.H3_RESOLUTION)
        for lat, lon in zip(lat_flat[mask], lon_flat[mask])
    ]

    df = pd.DataFrame({"h3_cell": cells, "value": val_flat[mask]})
    agg = df.groupby("h3_cell", as_index=False)["value"].mean()
    agg["observed_at"] = observed_at
    return agg
