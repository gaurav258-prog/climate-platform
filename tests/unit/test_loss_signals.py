"""Which loss figure leads (services.loss.signals.lead) — the decisions of 2026-10-16 and 2026-10-22: a storm figure is
its expected yearly loss; a flood figure is the one the institution states leads — with defences, or without them —
and where the protection map holds no level, the figure without defences, marked 'protection unknown'. Not stated:
no flood figure leads, so none is carried. No database."""
from __future__ import annotations

from services.loss.signals import lead


def _f(peril, defended=True):
    return {"peril": peril, "eal_eur": 100.0, "eal_low_eur": 60.0, "eal_high_eur": 150.0,
            "eal_defended_eur": 40.0 if defended else None, "eal_defended_low_eur": 20.0 if defended else None,
            "eal_defended_high_eur": 70.0 if defended else None}


def test_a_storm_figure_leads_with_its_expected_yearly_loss_whatever_the_flood_choice():
    for headline in (None, "defended", "undefended"):
        assert lead(_f("storm"), headline) == {"basis": None, "eur": 100.0, "low": 60.0, "high": 150.0}


def test_a_flood_figure_waits_for_the_stated_lead():
    assert lead(_f("flood"), None) is None


def test_a_flood_figure_leads_with_the_stated_figure():
    assert lead(_f("flood"), "defended") == {"basis": "defended", "eur": 40.0, "low": 20.0, "high": 70.0}
    assert lead(_f("flood"), "undefended") == {"basis": "undefended", "eur": 100.0, "low": 60.0, "high": 150.0}


def test_where_no_protection_level_is_known_the_undefended_figure_leads_marked_so():
    assert lead(_f("flood", defended=False), "defended") == {"basis": "protection_unknown", "eur": 100.0, "low": 60.0,
                                                             "high": 150.0}
