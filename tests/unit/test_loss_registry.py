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
