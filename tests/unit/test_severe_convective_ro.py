from __future__ import annotations

import numpy as np
import pandas as pd

from services.validation.engine import REGISTRY
import services.validation.validators.severe_convective_ro as m


def test_registered():
    assert "severe_convective_ro" in REGISTRY


def test_annual_probability_counts_years_not_reports():
    lat = np.array([30.0, 30.25]); lon = np.array([-100.0, -99.75])
    df = pd.DataFrame({"yr": [2014, 2014, 2014, 2015], "slat": [30.0] * 4, "slon": [-100.0] * 4})
    p = m.annual_probability(df, (2014, 2015), lat, lon, np.arange(2), np.arange(2), (2, 2))
    assert p[0, 0] == 1.0 and p[1, 1] == 0.0
    p = m.annual_probability(df, (2014, 2017), lat, lon, np.arange(2), np.arange(2), (2, 2))
    assert p[0, 0] == 0.5


def test_module_never_writes_anchor():
    src = open(m.__file__).read()
    assert "write_text" not in src and "json.dump" not in src
