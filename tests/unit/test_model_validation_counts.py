"""Model validation's counting rules, without a database: an event counts once per place however many of its
observations fall near it (a cyclone's track positions were counted as storms), and every key the validation record
uses for a test maps to one hazard on the register and one test design."""
from __future__ import annotations

import numpy as np

from core.hazard_taxonomy import EU_TAXONOMY, EXTRA_CHANNELS
from core.types import HazardType
from services.intelligence.model_validation import (
    _LEDGER_CHANNEL,
    ALL_HAZARDS,
    DESIGNS,
    _event_counts,
    hazard_for_channel,
    ledger_design,
    ledger_hazard,
)


def test_an_event_counts_once_however_many_of_its_positions_are_near():
    cells_lat, cells_lon = np.array([10.0, 40.0]), np.array([20.0, 20.0])
    # one storm with three positions near the first place, a second storm with one; nothing near the second place
    ev_lat = np.array([10.0, 10.1, 10.2, 10.05])
    ev_lon = np.array([20.0, 20.1, 19.9, 20.0])
    ev_id = np.array([0, 0, 0, 1])
    assert list(_event_counts(cells_lat, cells_lon, ev_lat, ev_lon, ev_id, 150.0)) == [2, 0]


def test_every_record_key_names_one_register_hazard():
    for key in _LEDGER_CHANNEL:
        assert ledger_hazard(key) is not None, key
    for h in HazardType:
        reg = hazard_for_channel(h.value)
        assert reg is not None and reg in (*EU_TAXONOMY, *EXTRA_CHANNELS), h
    assert all(ledger_hazard(k) is None for k in ALL_HAZARDS)
    assert ledger_hazard("not_a_hazard") is None


def test_a_test_falls_in_one_design():
    assert ledger_design("storm", "in_sample") == "same_record"
    assert ledger_design("storm", "temporal_holdout") == "held_out"
    assert ledger_design("flood", "out_of_sample") == "independent"
    assert ledger_design("crop_drought", "loo_cv") == "harvests"
    assert ledger_design("agri_spei", "observational") == "harvests"
    assert ledger_design("drought", "event_reproduction") == "events"
    assert ledger_design("flood", "a_new_method") is None
    assert {ledger_design(h, m) for h, m in [("storm", "in_sample"), ("storm", "temporal_holdout"), ("flood", "out_of_sample"),
                                             ("crop_heat", "loo_cv"), ("heat_acute", "event_reproduction")]} == set(DESIGNS)
