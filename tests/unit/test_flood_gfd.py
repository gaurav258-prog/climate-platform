"""GFD flood validator — cell aggregation, capping, registration."""
from __future__ import annotations

import numpy as np
import pandas as pd

from services.validation.engine import REGISTRY
from services.validation.validators import flood_gfd as F


def test_registered():
    assert "flood_gfd_global" in REGISTRY


def test_aggregate_block_share_and_masks():
    fl = np.array([[1, 0, 1, 1], [1, 1, np.nan, 1]], dtype="float32")
    vw = np.array([[5, 5, 5, 0], [5, 5, 5, 5]], dtype="float32")        # (0,3) not seen by MODIS
    wt = np.array([[0, 0, 0, 0], [1, 0, 0, 0]], dtype="float32")        # (1,0) permanent water
    lats = np.array([0.10, 0.05]); lons = np.array([0.05, 0.10, 0.30, 0.35])
    d = F.aggregate_block(fl, vw, wt, lats, lons)
    assert d[(0, 0)] == (3, 2)        # valid: (0,0),(0,1),(1,1); flooded: (0,0),(1,1)
    assert d[(0, 1)] == (2, 2)        # valid: (0,2),(1,3); (0,3) unseen, (1,2) NaN
    assert F.aggregate_block(fl * np.nan, vw, wt, lats, lons) == {}


def test_cap_per_region_seeded_and_stable():
    df = pd.DataFrame({"iy": range(50), "ix": 0, "region": ["a"] * 30 + ["b"] * 20})
    a = F.cap_per_region(df, 10, 3); b = F.cap_per_region(df, 10, 3)
    assert a.equals(b) and a.region.value_counts().to_dict() == {"a": 10, "b": 10}
