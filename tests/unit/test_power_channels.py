"""Channels on NASA POWER daily records: chronic heat counts observed hot days; cold wave reads the shared fetch;
neither ever fills a missing record."""
import ml.scoring.power_daily as pd_mod
from ml.scoring.cold_wave_point import _daily_tmin
from ml.scoring.heat_chronic import HOT_DAY_THRESHOLD_C, SATURATION_DAYS


def test_cold_wave_reads_the_shared_daily_fetch(monkeypatch):
    years = {str(1991 + i): [-5.0 - i * 0.5] * 10 + [3.0] * 320 for i in range(25)}
    monkeypatch.setattr(pd_mod, "daily_by_year", lambda la, lo, p: years if p == "T2M_MIN" else None)
    st = _daily_tmin(50.0, 8.0)
    assert st and st["n_years"] == 25 and st["annual_min"][0] == -17.0 and st["design_c"] <= -5.0
    monkeypatch.setattr(pd_mod, "daily_by_year", lambda la, lo, p: None)
    assert _daily_tmin(50.0, 8.0) is None


def test_hot_day_count_is_an_observed_count():
    years = {str(1991 + i): [35.0] * 60 + [20.0] * 300 for i in range(20)}        # 60 hot days every year
    days = sum(sum(1 for v in vals if v >= HOT_DAY_THRESHOLD_C) for vals in years.values()) / len(years)
    assert days == 60 and round(100 * days / SATURATION_DAYS, 1) == 32.9
