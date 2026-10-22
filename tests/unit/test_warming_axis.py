"""The platform's one timeline (services.reference.warming_axis; the product owner's decisions of 2026-10-22, E316):
global warming above 1995–2014 from the IPCC AR6 assessment and the HadCRUT5 record, read from committed, checksummed
files — and no warming number typed in the code that reads it."""
from __future__ import annotations

import pytest

from services.reference import warming_axis as W


def test_the_assessed_series_is_the_ipccs():
    """IPCC AR6 WG1: 'the assessed best global surface air temperature (GSAT) estimate (0.9°C and 3.5°C relative to
    1995–2014 for SSP1-2.6 and SSP5-8.5' for 2081–2100, very likely range up to '4.8°C for SSP5-8.5' (Figure 4.41
    caption). The file ends in 2099, so 2081–2100 is measured to 2099."""
    hot, low = W.anchor("hot_house_3_5c", "2100"), W.anchor("orderly_1_5c", "2100")
    assert round(hot["central"], 1) == 3.4 and round(low["central"], 1) == 0.9
    assert hot["low"] < hot["central"] < hot["high"] and round(hot["high"], 1) == 4.7


def test_a_source_file_that_changed_is_refused(monkeypatch):
    spec = W.spec()
    bad = {**spec, "observed": {**spec["observed"], "sha256": "0" * 64}}
    monkeypatch.setattr(W, "spec", lambda: bad)
    W._observed.cache_clear()
    with pytest.raises(W.AxisError):
        W._observed()
    W._observed.cache_clear()


def test_a_window_of_observations_cannot_reach_the_future():
    assert W.window("observed", 1960, 1999)["central"] < 0 < W.window("assessed", 2015, 2050, "ssp585")["central"]
    assert W.window("observed", W.current_year(), W.current_year() + 5) is None


def test_bracket_reads_the_nearest_below_and_above():
    levels = {"present": -0.4, "a": 0.6, "b": 1.1, "c": 1.5}
    assert W.bracket(0.6, levels) == ("a", "a", 0.0)                     # on a dataset: that dataset alone
    lo, hi, w = W.bracket(1.2, levels)
    assert (lo, hi) == ("b", "c") and w == pytest.approx(0.25)
    assert W.bracket(1.6, levels) is None                                # warmer than every dataset: a named gap
    with pytest.raises(W.AxisError):
        W.bracket(-1.0, levels)                                          # colder than every dataset: refused


@pytest.mark.parametrize("path", ["services/reference/warming_axis.py", "services/intelligence/gwl.py",
                                  "services/loss/timeline.py"])
def test_no_warming_number_is_typed_in_the_code(path):
    from tests.unit.test_money_parameters import _numbers
    assert _numbers(path) == [], f"{path} holds numbers the timeline's reference file should hold"


def test_the_present_year_is_declared_once():
    from services.intelligence import horizon
    assert horizon.NOW_YEAR == W.current_year() and horizon.ANCHORS[0] == (W.current_year(), "current")
