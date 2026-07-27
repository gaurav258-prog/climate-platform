"""EUDR determination engine (services/intelligence/eudr.py) — the decision logic.

Forest reads are mocked so these run fast and offline: they pin how commodity coverage,
geolocation sufficiency, and forest-loss combine into the honest status.
"""
import pytest

from services.intelligence import eudr as E
from services.intelligence.forest import ForestLoss

SMALL_SQ = {"type": "Polygon", "coordinates": [[[-1.6060, 6.6940], [-1.6047, 6.6940],
            [-1.6047, 6.6952], [-1.6060, 6.6952], [-1.6060, 6.6940]]]}


def _fl(has_loss=False, insufficient=False, first=None, loss_ha=0.0):
    return ForestLoss(has_loss=has_loss, loss_pixels=1 if has_loss else 0, total_pixels=100,
                      loss_ha=loss_ha, loss_fraction=0.0, first_loss_year=first, tile="10N_010W",
                      cutoff_year=2020, source="GFC-2024-v1.12 (mock)", insufficient=insufficient)


@pytest.fixture
def no_loss(monkeypatch):
    monkeypatch.setattr(E, "forest_loss_since", lambda *a, **k: _fl())


def test_non_covered_commodity_skips_forest(monkeypatch):
    # Must NOT call the forest layer for a commodity outside EUDR scope.
    monkeypatch.setattr(E, "forest_loss_since", lambda *a, **k: pytest.fail("should not read forest"))
    d = E.determine_plot(eudr_covered=False, latitude=6.69, longitude=-1.60)
    assert d.status == E.NOT_COVERED


def test_deforestation_free_when_no_loss(no_loss):
    d = E.determine_plot(eudr_covered=True, latitude=6.69, longitude=-1.60, area_ha=2.0)
    assert d.status == E.DEFORESTATION_FREE and d.geolocation == "point"


def test_non_compliant_when_loss(monkeypatch):
    monkeypatch.setattr(E, "forest_loss_since", lambda *a, **k: _fl(has_loss=True, first=2022, loss_ha=0.8))
    d = E.determine_plot(eudr_covered=True, plot_geometry=SMALL_SQ)
    assert d.status == E.NON_COMPLIANT and d.first_loss_year == 2022 and d.loss_ha == 0.8
    assert d.geolocation == "polygon"


def test_point_over_4ha_is_geolocation_incomplete(monkeypatch):
    monkeypatch.setattr(E, "forest_loss_since", lambda *a, **k: pytest.fail("should not read forest"))
    d = E.determine_plot(eudr_covered=True, latitude=6.69, longitude=-1.60, area_ha=9.0)
    assert d.status == E.GEO_INCOMPLETE


def test_insufficient_when_forest_unreadable(monkeypatch):
    monkeypatch.setattr(E, "forest_loss_since", lambda *a, **k: _fl(insufficient=True))
    d = E.determine_plot(eudr_covered=True, latitude=6.69, longitude=-1.60, area_ha=1.0)
    assert d.status == E.INSUFFICIENT


def test_no_geolocation_is_insufficient(no_loss):
    d = E.determine_plot(eudr_covered=True)
    assert d.status == E.INSUFFICIENT


def test_as_row_is_persistable(monkeypatch):
    monkeypatch.setattr(E, "forest_loss_since", lambda *a, **k: _fl(has_loss=True, first=2023, loss_ha=0.5))
    row = E.determine_plot(eudr_covered=True, plot_geometry=SMALL_SQ).as_row()
    assert row["eudr_determination"] == E.NON_COMPLIANT and row["eudr_first_loss_year"] == 2023
    assert "eudr_evidence" in row
