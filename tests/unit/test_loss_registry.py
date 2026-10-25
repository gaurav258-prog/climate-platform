"""E169: the loss foundation's registries are sound and agree with the schema."""
import importlib.util
from pathlib import Path

import pytest

from services.loss import registry

ROOT = Path(__file__).resolve().parents[2]


def _migration():
    path = ROOT / "core/db/migrations/versions/loss_found_20261006.py"
    spec = importlib.util.spec_from_file_location("loss_found", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_registries_are_sound():
    assert registry.check() == []


def test_the_schema_holds_exactly_the_registered_occupancy_classes():
    assert tuple(_migration().OCCUPANCY) == registry.occupancy_classes()


def test_the_schema_holds_the_scenario_and_horizon_vocabulary_of_the_scores():
    from core.types import SCENARIO_VALUES, TIME_HORIZON_VALUES
    m = _migration()
    assert set(m.SCENARIOS) == set(SCENARIO_VALUES)
    assert set(m.HORIZONS) == set(TIME_HORIZON_VALUES)


def test_a_stated_occupancy_wins_and_an_ambiguous_type_is_never_guessed():
    assert registry.occupancy_of("industrial", "portfolio_entities.entity_type", "residential_real_estate") == \
        ("industrial", "stated")
    assert registry.occupancy_of(None, "portfolio_entities.entity_type", "residential_real_estate")[0] == "residential"
    occ, why = registry.occupancy_of(None, "portfolio_entities.entity_type", "logistics")
    assert occ is None and "does not determine" in why
    with pytest.raises(registry.RegistryError):
        registry.occupancy_of("hotel", "portfolio_entities.entity_type", None)


def test_a_layer_must_be_registered():
    assert registry.layer("jrc_river_flood")["unit"] == "m"
    with pytest.raises(registry.RegistryError):
        registry.layer("no_such_layer")


def test_a_registry_change_reaches_a_running_process(tmp_path, monkeypatch):
    """E179: the Loss page kept showing the European maps as a candidate after their check put them in use — the API
    had parsed the registry once for its whole life. A registry file is now re-read whenever it changes on disk."""
    import json
    import os
    import shutil
    for name in ("hazard_intensity_layers.json", "event_sets.json", "occupancy.json", "loss_protocol.json"):
        shutil.copy(registry.REF / name, tmp_path / name)
    monkeypatch.setattr(registry, "REF", tmp_path)
    assert registry.layer("jrc_river_flood")["version"] == registry.layers()["jrc_river_flood"]["version"]
    f = tmp_path / "hazard_intensity_layers.json"
    doc = json.loads(f.read_text())
    doc["layers"]["jrc_river_flood"]["version"] = "changed-by-another-process"
    f.write_text(json.dumps(doc))
    st = f.stat()
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))      # a later version of the file, whatever the clock
    assert registry.layer("jrc_river_flood")["version"] == "changed-by-another-process"


def test_a_recorded_curve_test_reaches_a_running_process(tmp_path, monkeypatch):
    import json
    import os
    import shutil

    from services.loss import curves
    for p in curves.DIR.glob("*.json"):
        shutil.copy(p, tmp_path / p.name)
    monkeypatch.setattr(curves, "DIR", tmp_path)
    before = set(curves.families()) | set(curves.refused())
    if not before:
        pytest.skip("no curve family is built on this machine")
    name = sorted(tmp_path.glob("*.json"))[0]
    doc = json.loads(name.read_text())
    doc["family"] = doc["family"] + "_renamed"
    name.write_text(json.dumps(doc))
    st = name.stat()
    os.utime(name, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    assert set(curves.families()) | set(curves.refused()) != before


def test_a_layer_reads_in_a_curves_metric_only_by_a_registered_conversion():
    """Product owner's decision (2026-10-20): STORM's 10-minute wind is divided by 0.88 — undoing STORM's own step —
    to read it in the 1-minute wind the cyclone curves are stated in; no other conversion is guessed."""
    from services.loss import registry
    assert registry.divisor("storm_v4_wind", "max_sustained_wind_10min") == 1.0
    assert registry.divisor("storm_v4_wind", "max_sustained_wind_1min") == 0.88
    assert registry.divisor("storm_v4_wind", "max_sustained_wind_3s") is None
    assert ("storm", "max_sustained_wind_1min", "m/s") in registry.measures()
    c = registry.layer("storm_v4_wind")["conversions"]["max_sustained_wind_1min"]
    assert "multiplied by a factor of 0.88" in c["basis"] and any("1555" in x["title"] for x in c["sources"])


def test_a_conversion_without_its_decision_basis_or_sources_is_refused(monkeypatch):
    import copy

    from services.loss import registry
    L = copy.deepcopy(registry.layers())
    L["storm_v4_wind"]["conversions"]["max_sustained_wind_1min"] = {"divide_by": 0}
    monkeypatch.setattr(registry, "layers", lambda: L)
    problems = " | ".join(registry.check())
    assert "needs a positive divisor" in problems and "needs its decision, its quoted basis and its sources" in problems


def test_the_cyclone_curves_are_usable_only_through_the_registered_conversion(monkeypatch):
    import copy
    import json

    from services.loss import curves, registry
    doc = json.loads((curves.DIR / "eberenz_2021_tdr.json").read_text(encoding="utf-8"))
    assert not any("no intensity layer" in p for p in curves.check_family(doc))
    L = copy.deepcopy(registry.layers())
    for layer in L.values():                       # every storm wind layer: the present set and the future set
        if layer["peril"] == "storm":
            layer.pop("conversions")
    monkeypatch.setattr(registry, "layers", lambda: L)
    assert any("no intensity layer measures storm as max_sustained_wind_1min" in p for p in curves.check_family(doc))


def test_an_event_set_s_url_is_its_record_s(monkeypatch):
    import copy

    from services.loss import registry
    E = copy.deepcopy(registry.event_sets())
    E["storm_cc"]["url"] = "https://data.4tu.nl/articles/dataset/STORM_climate_change_tracks/99999999"
    monkeypatch.setattr(registry, "event_sets", lambda: E)
    assert any("its url must be its record's" in p and "14237678" in p for p in registry.check())
