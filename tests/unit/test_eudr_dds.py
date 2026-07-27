"""EUDR DDS assembler (services/intelligence/eudr_dds.py) — readiness + blocker gating.

A tiny fake session returns canned operator + plot rows so the assembly logic is tested without
a database. Pins the honesty gate: only deforestation-free plots are fileable, everything else is
an explicit blocker, and the operator's still-required fields are surfaced.
"""
from services.intelligence.eudr_dds import assemble_dds


class _Result:
    def __init__(self, rows): self._rows = rows
    def mappings(self): return self
    def first(self): return self._rows[0] if self._rows else None
    def all(self): return self._rows


class _FakeSession:
    def __init__(self, operator, plots): self._operator, self._plots = operator, plots
    def execute(self, stmt, params=None):
        sql = str(stmt)
        if "FROM organizations" in sql:
            return _Result([self._operator])
        return _Result(self._plots)


OP_FULL = {"legal_name": "Terra Foods", "name": "Terra", "eori": "ES123",
           "operator_address": "Madrid", "country": "ES"}
OP_NO_EORI = {**OP_FULL, "eori": None}


def _plot(name, det, commodity="Cocoa", hs="1801", country="GH", area=2.0, year=None):
    return {"plot_id": name, "plot_name": name, "country": country, "plot_geometry": None,
            "lat": 6.7, "lon": -1.6, "area_ha": area, "eudr_determination": det,
            "eudr_first_loss_year": year, "eudr_forest_source": "GFC-2024-v1.12",
            "commodity": commodity, "hs_code": hs}


def test_ready_when_all_free_and_operator_complete():
    s = _FakeSession(OP_FULL, [_plot("A", "deforestation_free"), _plot("B", "deforestation_free")])
    dds = assemble_dds(s, "org")
    assert dds["ready"] and dds["fileable_plots"] == 2 and not dds["blockers"]
    assert dds["items"][0]["hs_code"] == "1801" and dds["items"][0]["countries_of_production"] == ["GH"]


def test_non_compliant_plot_blocks_and_is_excluded():
    s = _FakeSession(OP_FULL, [_plot("A", "deforestation_free"), _plot("B", "non_compliant", year=2022)])
    dds = assemble_dds(s, "org")
    assert not dds["ready"] and dds["fileable_plots"] == 1
    assert len(dds["blockers"]) == 1 and dds["blockers"][0]["plot"] == "B"
    assert "2022" in dds["blockers"][0]["reason"]


def test_missing_operator_identity_blocks_readiness():
    s = _FakeSession(OP_NO_EORI, [_plot("A", "deforestation_free")])
    dds = assemble_dds(s, "org")
    assert not dds["ready"]
    assert any("eori" in c for c in dds["operator_completes"])


def test_geolocation_incomplete_is_a_blocker():
    s = _FakeSession(OP_FULL, [_plot("A", "geolocation_incomplete", area=9.0)])
    dds = assemble_dds(s, "org")
    assert not dds["ready"] and dds["fileable_plots"] == 0
    assert "polygon" in dds["blockers"][0]["reason"]


def test_not_determined_plot_is_a_blocker():
    s = _FakeSession(OP_FULL, [_plot("A", None)])
    dds = assemble_dds(s, "org")
    assert not dds["ready"] and dds["blockers"][0]["determination"] == "not_determined"
