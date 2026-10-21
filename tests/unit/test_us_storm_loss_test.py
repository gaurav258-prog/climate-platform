"""The US storm loss test (data/reference/loss_protocol.json 'us_storm_loss_test'): the code applies the registered
selection, NOAA's amounts are all read (E305), damage is priced in one year's dollars and placed by forecast office, surge
adds only to the information figure, and the modelled figure is the asset-weighted mean of the curve's yearly damage."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from services.loss import curves, engine, registry
from services.loss import us_storm_loss_test as T


def test_the_code_applies_the_registered_selection():
    p = T.protocol()
    for s in T.STATES:
        assert f" {s}," in p["data"]["states"] or f" {s} " in p["data"]["states"]
    assert "1996–2025" in p["data"]["damage"] and T.YEARS == (1996, 2025)
    assert "2024 dollars" in p["observed"] and T.BASE_YEAR == 2024
    for t in (*T.WIND, *T.SURGE):
        assert f"'{t}'" in p["data"]["damage"]
    assert "office area" in p["amended_before_run"]
    fams = curves.families()
    assert all(any(c["key"] == k for f in T.FAMILIES for c in fams[f]["curves"]) for k in p["curves"])


@pytest.mark.parametrize("raw,dollars", [("25.00K", 25_000), ("1.5M", 1_500_000), (".5M", 500_000), (".2B", 200_000_000),
                                         ("0", 0), ("0.00K", 0), ("", 0), (None, 0), (float("nan"), 0)])
def test_every_amount_noaa_writes_is_read(raw, dollars):
    """E305: NOAA writes some amounts without a leading zero ('.5M', '.2B'); the first parser set them aside."""
    assert T.money(raw) == dollars


@pytest.mark.parametrize("raw", ["K", "1.2.3M", "5H", "abc"])
def test_an_amount_not_written_as_noaa_states_is_not_guessed(raw):
    assert T.money(raw) is None


def _cells():
    return pd.DataFrame({"office": ["MOB", "MOB", "LIX"], "value": [100.0, 300.0, 1000.0]})


def test_damage_is_priced_in_2024_dollars_placed_by_office_and_surge_is_information_only(monkeypatch):
    monkeypatch.setattr(T, "cpi_yearly", lambda: {2004: 100.0, 2024: 200.0})
    wind = (pd.DataFrame({"office": ["MOB", "LIX", "EYW"], "year": [2004, 2024, 2004], "dollars": [60.0, 300.0, 1.0]}),
            {"damage_unreadable": 0})
    surge = (pd.DataFrame({"office": ["LIX"], "year": [2024], "dollars": [600.0]}), {"damage_unreadable": 0})
    out, sel = T.observed(_cells(), {"MOB", "LIX"}, wind=wind, surge=surge)
    assert out["MOB"]["assets"] == 400.0
    assert out["MOB"]["rate"] == pytest.approx(60 * 2 / 30 / 400)          # 2004 dollars doubled to 2024
    assert out["LIX"]["rate"] == pytest.approx(300 / 30 / 1000)
    assert out["LIX"]["rate_with_surge"] == pytest.approx(900 / 30 / 1000)  # surge only in the information figure
    assert out["MOB"]["records"] == 1 and out["LIX"]["records"] == 1
    assert sel["wind_set_aside"]["office_not_in_2025_outlines"] == ["EYW"]
    assert sel["wind_set_aside"]["their_damage_2024_usd"] == 2               # 0.5% of the damage: under the 1% check


def test_damage_in_a_year_without_twelve_price_indexes_stops_the_run(monkeypatch):
    monkeypatch.setattr(T, "cpi_yearly", lambda: {2024: 200.0})
    wind = (pd.DataFrame({"office": ["MOB"], "year": [2025], "dollars": [1.0]}), {"damage_unreadable": 0})
    empty = (pd.DataFrame({"office": [], "year": [], "dollars": []}), {"damage_unreadable": 0})
    with pytest.raises(RuntimeError, match="no twelve CPI-U indexes"):
        T.observed(_cells(), {"MOB"}, wind=wind, surge=empty)


def test_the_modelled_figure_is_the_asset_weighted_mean_of_the_curves_yearly_damage():
    fam = curves.families().get("eberenz_2021_tdr")
    if fam is None:
        pytest.skip("the cyclone family is not built on this machine")
    cv = next(c for c in fam["curves"] if c["key"] == "eberenz_2021_tdr:all:NA2")
    rps = registry.layer(T.LAYER)["return_periods"]
    w = np.array([np.linspace(20, 60, len(rps)), np.linspace(10, 40, len(rps)), np.linspace(30, 70, len(rps))])
    got = T.modelled(_cells(), w, cv)

    def ead(row):
        return engine.eal({rp: curves.ratio(cv["points"], x / 0.88) for rp, x in zip(rps, row)})
    assert got["MOB"] == pytest.approx((100 * ead(w[0]) + 300 * ead(w[1])) / 400)
    assert got["LIX"] == pytest.approx(ead(w[2]))


def test_a_run_that_cannot_place_its_damage_is_refused(monkeypatch):
    """E306: 39% of the wind damage sat in zone codes the 2025 outlines no longer hold; the run now refuses rather than
    test on what is left."""
    monkeypatch.setattr(T, "cpi_yearly", lambda: {2024: 1.0})
    wind = (pd.DataFrame({"office": ["MOB", "XXX"], "year": [2024, 2024], "dollars": [90.0, 10.0]}), {"damage_unreadable": 0})
    empty = (pd.DataFrame({"office": [], "year": [], "dollars": []}), {"damage_unreadable": 0})
    with pytest.raises(RuntimeError, match="names an office the outlines do not hold"):
        T.observed(_cells(), {"MOB", "LIX"}, wind=wind, surge=empty)


def test_the_ledger_reads_a_cyclone_loss_result_as_the_tropical_cyclone_hazard():
    from services.intelligence.model_validation import ledger_hazard
    assert ledger_hazard("cyclone_loss").id == "cyclone"
