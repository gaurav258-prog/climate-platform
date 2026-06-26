"""
Tests for Sentinel-1 SAR and Sentinel-3 SLSTR stub modes.
No CDSE credentials required — stub mode reads from fixture CSVs.
"""
import os
import pytest

from core.types import HazardType


def test_sentinel1_stub_returns_observations(monkeypatch):
    monkeypatch.setenv("SENTINEL1_STUB", "true")
    from services.ingestion.adapters.sentinel1_sar import Sentinel1SARAdapter
    adapter = Sentinel1SARAdapter()
    raw = adapter.fetch()
    obs = adapter.to_observations(raw)

    assert len(obs) > 0
    assert all(o.hazard_type == HazardType.FLOOD.value for o in obs)
    assert all(o.raw_unit == "dB" for o in obs)
    assert all(o.source_provider == "sentinel1_sar_grd" for o in obs)


def test_sentinel1_stub_values_are_in_db_range(monkeypatch):
    monkeypatch.setenv("SENTINEL1_STUB", "true")
    from services.ingestion.adapters.sentinel1_sar import Sentinel1SARAdapter
    adapter = Sentinel1SARAdapter()
    obs = adapter.to_observations(adapter.fetch())

    # SAR backscatter for land/water: realistic range -30 dB to +5 dB
    for o in obs:
        assert -40.0 < float(o.raw_value) < 10.0, f"Unrealistic backscatter: {o.raw_value}"


def test_sentinel1_no_credentials_returns_empty(monkeypatch):
    monkeypatch.delenv("SENTINEL1_STUB", raising=False)
    monkeypatch.setattr("core.config.settings.COPERNICUS_USER", "")
    monkeypatch.setattr("core.config.settings.COPERNICUS_PASSWORD", "")
    from importlib import reload
    import services.ingestion.adapters.sentinel1_sar as m
    reload(m)
    adapter = m.Sentinel1SARAdapter()
    raw = adapter.fetch()
    assert raw == []


def test_sentinel3_stub_returns_lst_observations(monkeypatch):
    monkeypatch.setenv("SENTINEL3_STUB", "true")
    from services.ingestion.adapters.sentinel3_slstr import Sentinel3SLSTRAdapter
    adapter = Sentinel3SLSTRAdapter()
    obs = adapter.to_observations(adapter.fetch())

    assert len(obs) > 0
    assert all(o.hazard_type == HazardType.HEAT_ACUTE.value for o in obs)
    assert all(o.raw_unit == "K" for o in obs)


def test_sentinel3_stub_lst_in_realistic_range(monkeypatch):
    monkeypatch.setenv("SENTINEL3_STUB", "true")
    from services.ingestion.adapters.sentinel3_slstr import Sentinel3SLSTRAdapter
    adapter = Sentinel3SLSTRAdapter()
    obs = adapter.to_observations(adapter.fetch())

    # LST in Kelvin: realistic EU summer range 270 K (winter) to 340 K (extreme heat)
    for o in obs:
        assert 250.0 < float(o.raw_value) < 360.0, f"Unrealistic LST: {o.raw_value}"
