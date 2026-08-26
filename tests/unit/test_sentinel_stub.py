"""
Tests for Sentinel-1 SAR and Sentinel-3 SLSTR stub modes.
No CDSE credentials required — stub mode reads from fixture CSVs.
"""

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
    # the SAR adapter gates on the Sentinel Hub Statistical-API creds — clear those too, or a local .env that
    # actually has them (real deployment) makes this "no credentials" assertion fail for the wrong reason.
    monkeypatch.setattr("core.config.settings.SENTINEL_HUB_CLIENT_ID", "")
    monkeypatch.setattr("core.config.settings.SENTINEL_HUB_CLIENT_SECRET", "")
    from importlib import reload

    import services.ingestion.adapters.sentinel1_sar as m
    reload(m)
    adapter = m.Sentinel1SARAdapter()
    raw = adapter.fetch()
    assert raw == []


# ── Sentinel-1 flood closure: classification + CDSE Statistical API contract ─────────────────────────────

def test_flood_quality_classification():
    from services.ingestion.adapters.sentinel1_sar import OPEN_WATER_DB, flood_quality
    assert flood_quality(-6.0) == (0, None)                     # dry land → clean
    flag, note = flood_quality(-20.0)                           # open water → flagged
    assert flag == 1 and note and "open-water" in note
    assert flood_quality(OPEN_WATER_DB)[0] == 1                 # threshold is inclusive


def test_cell_geojson_is_valid_closed_polygon():
    import h3

    from services.ingestion.adapters.sentinel1_sar import _cell_geojson
    cell = h3.latlng_to_cell(51.5, -0.12, 8)
    g = _cell_geojson(cell)
    ring = g["coordinates"][0]
    assert g["type"] == "Polygon" and ring[0] == ring[-1] and len(ring) >= 4
    # GeoJSON is (lon, lat) order — longitudes near London are negative, latitudes ~51
    assert -1.0 < ring[0][0] < 1.0 and 50.0 < ring[0][1] < 53.0


def test_statistics_body_matches_cdse_contract():
    import h3

    from services.ingestion.adapters.sentinel1_sar import Sentinel1SARAdapter
    body = Sentinel1SARAdapter()._statistics_body(h3.latlng_to_cell(45.4, 12.3, 8))
    assert body["input"]["data"][0]["type"] == "sentinel-1-grd"
    assert body["input"]["data"][0]["processing"]["backCoeff"] == "GAMMA0_TERRAIN"
    agg = body["aggregation"]
    assert "evalscript" in agg and agg["timeRange"]["from"] < agg["timeRange"]["to"]
    assert body["input"]["bounds"]["geometry"]["type"] == "Polygon"


def test_stub_observations_carry_open_water_flag(monkeypatch):
    monkeypatch.setenv("SENTINEL1_STUB", "true")
    from services.ingestion.adapters.sentinel1_sar import OPEN_WATER_DB, Sentinel1SARAdapter
    obs = Sentinel1SARAdapter().to_observations([{"stub": True}])
    assert obs and any(o.quality_flag == 1 for o in obs)        # fixture includes an open-water reading
    for o in obs:
        assert o.quality_flag == (1 if float(o.raw_value) <= OPEN_WATER_DB else 0)


def test_sentinel1_no_sh_credentials_returns_empty(monkeypatch):
    """Without stub and without Sentinel Hub credentials, the live path lands nothing (honest planned feed)."""
    monkeypatch.delenv("SENTINEL1_STUB", raising=False)
    monkeypatch.setattr("core.config.settings.SENTINEL_HUB_CLIENT_ID", "")
    monkeypatch.setattr("core.config.settings.SENTINEL_HUB_CLIENT_SECRET", "")
    from services.ingestion.adapters.sentinel1_sar import Sentinel1SARAdapter
    assert Sentinel1SARAdapter().fetch() == []


def test_sentinel1_grd_flood_feed_registered_and_honest():
    """The imagery feed must exist and stay 'planned' (nothing lands without credentials) — no overstatement."""
    from services.data.feeds import FEEDS
    f = next(x for x in FEEDS if x["key"] == "imagery")
    assert f["maturity"] == "planned" and "SENTINEL_HUB" in f["note"]


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
