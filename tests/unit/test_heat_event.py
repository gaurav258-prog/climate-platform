"""Acute-heat metrics — the signal monthly means destroy.

Guards the finding that blocked the olive backtest: a two-week >40C heatwave through olive
flowering shows up in monthly data as a bland +3C anomaly, so no monthly index could explain
Spain's -30% 2022 crop anomaly. These metrics exist to see the spike.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from ml.features.heat_event import daily_tmax, heat_event_by_year


def _hourly(days_by_year: dict, base_c=25.0, hot_days=(), hot_c=42.0, ncell=3):
    """Synthetic hourly t2m (Kelvin) over a small grid, with chosen days forced hot."""
    times, vals = [], []
    for year, days in days_by_year.items():
        for d in range(days):
            day = pd.Timestamp(f"{year}-05-01") + pd.Timedelta(days=d)
            peak = hot_c if (year, d) in hot_days else base_c
            for h in range(24):
                times.append(day + pd.Timedelta(hours=h))
                # a diurnal cycle peaking at 14:00 so the daily MAX is the peak value
                vals.append(peak if h == 14 else peak - 8.0)
    arr = np.array(vals, dtype=float) + 273.15
    data = np.repeat(arr[:, None, None], ncell, axis=1).repeat(ncell, axis=2)
    return xr.Dataset(
        {"t2m": (("time", "latitude", "longitude"), data)},
        coords={"time": pd.DatetimeIndex(times),
                "latitude": np.linspace(37, 39, ncell),
                "longitude": np.linspace(-6, -4, ncell)},
    )


def test_daily_max_is_the_peak_not_the_mean():
    ds = _hourly({2022: 3}, base_c=25.0)
    tmax = daily_tmax(ds)
    assert len(tmax) == 3
    # the day peaks at 25C and sits at 17C otherwise: the daily MAX must be 25, not the mean
    assert float(tmax[0]) == pytest.approx(25.0, abs=0.01)


def test_consecutive_spell_is_distinguished_from_scattered_hot_days():
    """THE metric that matters biologically: 10 days in a row is a different event from 10
    hot days scattered across the month — flowers abort under a sustained spell."""
    scattered = _hourly({2001: 20}, hot_days={(2001, d) for d in (1, 4, 7, 10, 13)})
    run = _hourly({2002: 20}, hot_days={(2002, d) for d in (5, 6, 7, 8, 9)})

    a = heat_event_by_year(daily_tmax(scattered), [5], 35.0)[0]
    b = heat_event_by_year(daily_tmax(run), [5], 35.0)[0]

    assert a["hot_days"] == b["hot_days"] == 5      # identical by the naive count
    assert a["max_spell"] == 1                      # ...but nothing sustained
    assert b["max_spell"] == 5                      # ...vs a real two-week-style spell
    assert a["degree_days"] == pytest.approx(b["degree_days"])   # intensity also identical


def test_heatwave_is_visible_where_a_monthly_mean_would_hide_it():
    """31 days at 25C with a 14-day 42C spell averages ~32C — unremarkable. The acute metrics
    must still show the spell."""
    ds = _hourly({2022: 31}, base_c=25.0, hot_days={(2022, d) for d in range(10, 24)})
    r = heat_event_by_year(daily_tmax(ds), [5], 35.0)[0]
    assert r["mean_tmax_c"] < 34            # the monthly-mean view: nothing to see
    assert r["max_spell"] == 14             # the acute view: a two-week heatwave
    assert r["extreme_days"] == 14          # >= 40C
    assert r["hottest_day_c"] == pytest.approx(42.0, abs=0.01)


def test_one_hot_pixel_cannot_invent_a_regional_heatwave():
    """We take the region MEAN of per-cell daily maxima: a single scorching cell must not
    make the whole belt look like it had a heatwave."""
    ds = _hourly({2022: 10}, base_c=25.0)
    ds["t2m"][:, 0, 0] = 50.0 + 273.15          # one cell roasting all month
    r = heat_event_by_year(daily_tmax(ds), [5], 35.0)[0]
    assert r["hot_days"] == 0                    # 1 of 9 cells cannot carry the region mean
    assert r["max_spell"] == 0


def test_season_window_is_respected():
    ds = _hourly({2022: 40}, base_c=25.0, hot_days={(2022, d) for d in range(35, 40)})  # into June
    may = heat_event_by_year(daily_tmax(ds), [5], 35.0)[0]
    assert may["hot_days"] == 0                  # the June spell is outside a May-only window
    both = heat_event_by_year(daily_tmax(ds), [5, 6], 35.0)[0]
    assert both["hot_days"] == 5
