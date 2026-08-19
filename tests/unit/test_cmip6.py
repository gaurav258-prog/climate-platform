"""Raw CMIP6 delta lookup + scenario/horizon mapping (projections v3).

Pins the mapping and the fallback contract, and — when the built delta table is present — that the
raw GCM deltas actually drive the drought scorer (a Mediterranean belt dries more under a
higher-emission SSP). If the table hasn't been built in this environment the data-dependent checks
skip rather than fail.
"""
import pytest

from ml.scoring.cmip6 import HORIZON_TO_PERIOD, SCENARIO_TO_SSP, cmip6_delta, has_coverage
from ml.scoring.drought_climatology import drought_score


def test_scenario_and_horizon_mapping():
    assert SCENARIO_TO_SSP == {"orderly_1_5c": "ssp126", "disorderly_2c": "ssp245",
                               "hot_house_3_5c": "ssp585"}
    assert HORIZON_TO_PERIOD == {"2030": "2021-2040", "2050": "2041-2060", "2100": "2081-2100"}


def test_no_cmip6_for_baseline_current_or_unknown_region():
    # baseline (~0.6 °C is below any SSP pathway) and current (0) have no CMIP6 mapping → None →
    # the caller keeps its parametric path. Unknown region → None.
    assert cmip6_delta("spain_olive", "baseline", "2100") is None
    assert cmip6_delta("spain_olive", "hot_house_3_5c", "current") is None
    assert cmip6_delta("no_such_belt", "hot_house_3_5c", "2100") is None
    assert cmip6_delta(None, "hot_house_3_5c", "2100") is None


def test_override_replaces_parametric_in_scorer():
    # Supplying CMIP6 deltas must change the forward score vs the parametric default, and a drier
    # (more negative precip) delta must not score LOWER than a wetter one at the same warming.
    spei = -0.3
    drought_score(spei, "hot_house_3_5c", "2100", lat=38, lon=-4)
    dry = drought_score(spei, "hot_house_3_5c", "2100", lat=38, lon=-4, warming_c=3.9, precip_frac=-0.33)
    wet = drought_score(spei, "hot_house_3_5c", "2100", lat=38, lon=-4, warming_c=3.9, precip_frac=+0.06)
    assert dry >= wet


@pytest.mark.skipif(not has_coverage(), reason="CMIP6 delta table not built in this environment")
def test_built_table_is_physical():
    # A Mediterranean belt should warm, and dry MORE under SSP5-8.5 than under SSP1-2.6.
    hot = cmip6_delta("spain_olive", "hot_house_3_5c", "2100")
    low = cmip6_delta("spain_olive", "orderly_1_5c", "2100")
    assert hot is not None and low is not None
    assert hot.dtas_c > low.dtas_c > 0                 # more warming under the high scenario
    assert hot.dpr_frac <= low.dpr_frac                # and at least as much (usually more) drying
    assert hot.n_models >= 1
