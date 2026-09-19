from __future__ import annotations

import numpy as np

from services.validation.validators import loss_us as L


def test_parse_damage():
    assert L.parse_damage("10.00K") == 10_000.0
    assert L.parse_damage("1.5M") == 1_500_000.0
    assert L.parse_damage("0") == 0.0
    assert L.parse_damage(None) == 0.0
    assert L.parse_damage(float("nan")) == 0.0


def test_county_fips():
    assert L.county_fips("01", "001") == 1001
    assert L.county_fips(48, 201) == 48201
    assert L.county_fips(None, 1) is None


def test_sample_cells_deterministic():
    cells = [(i, i) for i in range(100)]
    a = L.sample_cells(cells, 10); b = L.sample_cells(list(reversed(cells)), 10)
    assert a == b and len(a) == 10
    assert L.sample_cells(cells[:5], 10) == cells[:5]


def test_nearest_within():
    lats = np.array([30.0, 40.0]); lons = np.array([-90.0, -100.0])
    assert L.nearest_within(30.1, -90.1, lats, lons, 0.5) == 0
    assert L.nearest_within(35.0, -95.0, lats, lons, 0.5) is None


def test_rma_parse_and_aggregate():
    l1 = "2015|01|AL|001|Autauga|0011|Wheat|02|RP|A|UH|11|Drought|04|APR|2015|1|1|5.775|.0|823.5|125.55|25.05|100.5|.0|.0|.0|5.55|791.4|6.30"
    l2 = "2015|01|AL|001|Autauga|0011|Wheat|02|RP|A|H |01|Decline in Price|07|JUL|2015|1|1|15.2675|.0|2177.13|331.855|66.185|265.67|.0|.0|.0|15.5|847.23|2.55"
    p = L.parse_rma_line(l1)
    assert p == (2015, 1001, "Drought", 823.5, 791.4)
    t = L.rma_county_table([l1, l2, "garbage"])
    assert t[1001]["ind_drought"] == 791.4
    assert abs(t[1001]["ind_all"] - (791.4 + 847.23)) < 1e-9
    assert abs(t[1001]["liab"] - (823.5 + 2177.13)) < 1e-9
