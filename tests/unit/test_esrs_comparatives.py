"""ESRS 1 chapter 7.1 per version (services.governance.esrs_comparatives), on a statement of three figures with the
previous period's sources stubbed: what each rule requires, and each relief only where the text grants it."""
from __future__ import annotations

from datetime import date

import pytest

import services.regspec as R
from services.governance import esrs_comparatives as C
from services.governance import esrs_document as D
from services.governance.esrs_binding import concepts_of
from services.governance.esrs_checks import phase_ins

V2023, V2026 = "dr_2023_2772_as_2025_1416", "dr_2026_1563"


def _sections(*concepts, std="E1", material=True):
    return [{"standard": std, "topic": {"material": material}, "items": [
        {"id": "E1-5", "kind": "heading"},
        *({"id": f"E1-5.{n}", "kind": "field", "status": "filled",
           "datapoints": [{"concept": c, "value": 10.0, "lane": "provided"}]} for n, c in enumerate(concepts))]}]


@pytest.fixture
def world(monkeypatch):
    w = {"reported": {}, "topics": None, "attested": {}, "answers": {}, "prev_version": V2026}
    monkeypatch.setattr(C, "_reported", lambda s, o, e, pe: {
        "source": "statement filed (submitted)" if w["reported"] or w["topics"] else None, "filing_id": "f",
        "figures": w["reported"], "topics": w["topics"]})
    monkeypatch.setattr(C, "_attested", lambda s, o, e, pe: w["attested"])
    monkeypatch.setattr(C, "read", lambda s, o, e, pe: w["answers"])
    monkeypatch.setattr(D, "governing", lambda s, o, pe: {"version": w["prev_version"]})
    return w


def _run(version, sections, first=2024, fy=2027):
    return C.compute(None, "org", None, date(fy, 12, 31), R.load("esrs", version), sections,
                     {"first_year": first, "employees": 1200.0, "turnover_eur": 500e6})


def test_a_figure_without_a_comparative_blocks_unless_impracticable(world):
    out = _run(V2026, _sections("e1.energy.total"))
    assert out["rows"][0]["status"] == "missing" and out["missing"] == ["e1.energy.total (§83)"]
    world["answers"] = {"cmp.e1.energy.total": {"impracticable": "not metered"}}
    out = _run(V2026, _sections("e1.energy.total"))
    assert out["rows"][0]["status"] == "impracticable" and not out["missing"]


def test_2026_a_revision_asks_whether_it_differs_significantly(world):
    world["reported"], world["attested"] = {"e1.energy.total": 100.0}, {"e1.energy.total": 104.0}
    out = _run(V2026, _sections("e1.energy.total"))
    assert out["rows"][0]["status"] == "state_significance" and out["rows"][0]["difference"] == 4.0
    world["answers"] = {"cmp.e1.energy.total": {"significant": False}}
    assert _run(V2026, _sections("e1.energy.total"))["rows"][0]["status"] == "revised"           # §87(a): not significant
    world["answers"] = {"cmp.e1.energy.total": {"significant": True}}
    assert _run(V2026, _sections("e1.energy.total"))["rows"][0]["status"] == "reason_missing"
    world["answers"] = {"cmp.e1.energy.total": {"significant": True, "reason": "metering error"}}
    assert _run(V2026, _sections("e1.energy.total"))["missing"] == []


def test_2023_any_revision_needs_its_reasons(world):
    world["reported"], world["attested"] = {"e1.energy.total": 100.0}, {"e1.energy.total": 104.0}
    out = _run(V2023, _sections("e1.energy.total"), fy=2026)
    assert out["rows"][0]["status"] == "reason_missing" and "§84(b)" in out["missing"][0]


def test_first_year_reliefs_follow_the_version_and_the_wave(world):
    # 2023 §136: the first year of preparation
    assert _run(V2023, _sections("e1.energy.total"), first=2025, fy=2025)["rows"][0]["status"] == "relief"
    assert _run(V2023, _sections("e1.energy.total"), first=2024, fy=2025)["rows"][0]["status"] == "missing"
    # 2026 §124, other undertakings (first year 2027): their first financial year
    assert _run(V2026, _sections("e1.energy.total"), first=2027, fy=2027)["rows"][0]["status"] == "relief"
    # 2026 §124, wave one in its first year under 2026/1563: only a metric not the same as one the first set required
    world["prev_version"] = V2023
    first_set = concepts_of(R.load("esrs", "dr_2023_2772"))
    new = next(c for c in sorted(concepts_of(R.load("esrs", V2026))) if c not in first_set)
    out = _run(V2026, _sections("e1.energy.total", new), first=2024, fy=2027)
    st = {r["concept"]: r["status"] for r in out["rows"]}
    assert st == {"e1.energy.total": "missing", new: "relief"}
    world["prev_version"] = V2026                       # its second year under 2026/1563: no relief
    assert _run(V2026, _sections(new), first=2024, fy=2028)["rows"][0]["status"] == "missing"


def test_an_unknown_first_year_is_named_not_assumed(world):
    out = C.compute(None, "org", None, date(2027, 12, 31), R.load("esrs", V2026), _sections("e1.energy.total"),
                    {"first_year": None, "employees": None, "turnover_eur": None})
    assert out["needs"] == ["csrd.first_reporting_year"] and out["rows"][0]["status"] == "missing"


def test_2026_a_topic_reported_for_the_first_time(world):
    world["topics"] = {"E1": False}                      # the previous statement assessed E1 not material
    assert _run(V2026, _sections("e1.energy.total"))["rows"][0]["status"] == "relief"
    world["topics"] = {"E1": True}
    assert _run(V2026, _sections("e1.energy.total"))["rows"][0]["status"] == "missing"
    world["topics"], world["answers"] = None, {"topic.E1": {"first_time": True}}     # no previous statement held: stated
    assert _run(V2026, _sections("e1.energy.total"))["rows"][0]["status"] == "relief"
    assert _run(V2023, _sections("e1.energy.total"), fy=2026)["rows"][0]["status"] == "missing"   # no such relief in 2023


def test_2023_a_phased_in_requirement_in_its_first_mandatory_year(world):
    """2023 ESRS 1 §136, second sentence: e1_6_scope3_total (≤ 750 employees, first year of preparation) — in the
    second year the datapoints are mandatory for the first time, so their comparative is not required."""
    rule = next(r for r in phase_ins(V2023) if r["id"] == "e1_6_scope3_total")
    item = rule["items"][0]
    secs = [{"standard": "E1", "topic": {"material": True}, "items": [
        {"id": "E1-6", "kind": "heading"},
        {"id": item, "kind": "field", "status": "filled", "datapoints": [{"concept": "e1.ghg.scope3.total", "value": 5.0}]}]}]
    facts = {"first_year": 2025, "employees": 600.0, "turnover_eur": None}
    out = C.compute(None, "org", None, date(2026, 12, 31), R.load("esrs", V2023), secs, facts)
    assert out["rows"][0]["status"] == "relief" and "e1_6_scope3_total" in out["rows"][0]["relief"]
    out = C.compute(None, "org", None, date(2026, 12, 31), R.load("esrs", V2023), secs, {**facts, "employees": 900.0})
    assert out["rows"][0]["status"] == "missing"                       # the phase-in never applied: no relief


def test_a_ratio_comparative_is_derived_from_the_previous_periods_inputs(monkeypatch):
    """E137: the previous period's ratios come from its attested inputs, as the current period's do — never 'missing'
    while every input is attested; a ratio the undertaking attests itself wins."""
    prov = {"e1.ghg.total.location": {"value": 200.0}, "e1.ghg.total.market": {"value": 150.0},
            "fs.net_revenue": {"value": 1e8, "value_eur": 1e8, "currency": "EUR"},
            "e3.water.consumption": {"value": 5000.0}, "e1.energy.mix@fossil": {"value": 3.0}}
    monkeypatch.setattr(D, "_provided", lambda s, o, e, pe: prov)
    att = C._attested(None, "org", None, date(2024, 12, 31))
    assert att["e1.ghg.intensity_net_revenue"] == {"location": 2e-6, "market": 1.5e-6}
    assert att["e3.water.intensity"] == pytest.approx(50.0)
    assert "e1.energy.intensity_high_impact" not in att                   # inputs not attested: no figure, no guess
    assert att["e1.energy.mix"] == {"fossil": 3.0}
    prov["e3.water.intensity"] = {"value": 49.0}
    assert C._attested(None, "org", None, date(2024, 12, 31))["e3.water.intensity"] == 49.0
