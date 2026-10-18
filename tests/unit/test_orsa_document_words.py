"""E217: the ORSA climate analysis prints scenarios, horizons, perils and the at-risk threshold in words — the document's
reader (the undertaking, its supervisor) never sees a scenario key, a hazard key or a settings key. The values a filing
freezes keep their codes; only what is printed is named."""
import re

import pytest

from core.messages import INTERNAL
from services.governance.orsa_climate import computed_value

DOTTED = re.compile(r"\b[a-z]{2,}\.[a-z_]{2,}\b")


def _orsa(projected: bool) -> dict:
    run = lambda sc, hz: {"scenario": sc, "horizon": hz, "expected_annual_loss_eur": 120.0,          # noqa: E731
                          "change_net_1_in_200_eur": 5000, "change_net_1_in_200_pct_of_own_funds": 1.2}
    runs = [run(sc, hz) for sc in ("orderly_1_5c", "hot_house_3_5c") for hz in ("2030", "2050", "2100")]
    return {
        "scenarios": {"below_2c": {"label": "Orderly transition (NGFS archetype), SSP1-2.6", "warming_2081_2100_c": 1.8,
                                   "very_likely_c": [1.3, 2.4]},
                      "above_2c": {"label": "Hot house world (NGFS archetype), SSP5-8.5", "warming_2081_2100_c": 4.4,
                                   "very_likely_c": [3.3, 5.7]}},
        "runs": runs, "today": {"expected_annual_loss_eur": 100.0},
        "capital": {"scr_ratio_pct": 183.3, "eligible_own_funds_scr": 1e9},
        "materiality": {"sum_insured_eur": 1e9, "largest_sum_insured_at_high_hazard_pct": None,
                        "worst": {"scenario": "hot_house_3_5c", "horizon": "2100", "change_net_1_in_200_eur": 5000,
                                  "change_net_1_in_200_pct_of_own_funds": 1.2}},
        "largest_zone_event": {"hazard": "coastal_flood", "region": "Valencia/València", "event_loss_eur": 9000,
                               "projected": projected, "event_loss_above_2c_eur": 12000},
        "above_2c_last_horizon": ["hot_house_3_5c", "2100"],
        "perils": [{"hazard": h, "projected": h not in ("seismic", "unknown"), "expected_annual_loss_today_eur": 10.0,
                    "expected_annual_loss_above_2c_eur": 12.0}
                   for h in ("flood", "heavy_precip", "severe_convective", "coastal_flood", "seismic", "unknown")],
        "readings": [{"subject": "Capital impact", "reading": "The standard-formula nat-cat factors do not move."}],
    }


def _printed(v: dict) -> list[str]:
    t = v.get("table") or {}
    return [v.get("text") or "", t.get("note") or "", *[str(x) for r in t.get("rows", []) for x in r.values()]]


@pytest.mark.parametrize("projected", [True, False])
@pytest.mark.parametrize("item", ["scenarios", "scenarios.below_2c", "scenarios.above_2c", "materiality.demonstration",
                                  "impact"])
def test_the_document_prints_no_key(item, projected):
    for line in _printed(computed_value(item, _orsa(projected))):
        assert not INTERNAL.search(line) and not DOTTED.search(line), line


def test_the_impact_table_names_its_scenarios_and_today():
    rows = computed_value("impact", _orsa(True))["table"]["rows"]
    assert (rows[0]["scenario"], rows[0]["horizon"]) == ("Current climate", "Today")
    assert {r["scenario"] for r in rows[1:]} == {"Orderly 1.5 °C", "Hot house 3.5 °C"}


def test_a_missing_threshold_is_said_in_words():
    text = computed_value("materiality.demonstration", _orsa(True))["text"]
    assert "the undertaking's at-risk threshold is not yet stated" in text and "Sea-level rise" in text
