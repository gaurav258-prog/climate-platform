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
