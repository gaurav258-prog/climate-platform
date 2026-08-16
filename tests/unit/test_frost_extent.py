"""Frost-extent severity band + the committed frost-severity climatology (separate frost hazard signal)."""
import json
import os

from ml.scoring.frost_extent import severity_band


def test_severity_band_boundaries():
    assert severity_band(0.60) == "severe"      # 1994-scale catastrophic frost
    assert severity_band(0.30) == "severe"      # band floor
    assert severity_band(0.15) == "elevated"
    assert severity_band(0.03) == "normal"      # ordinary winter
    assert severity_band(0.0) == "normal"
    assert severity_band(None) == "unknown"


def test_brazil_coffee_frost_climatology_sane():
    """The committed climatology must correctly identify the real severe frosts, not a saturated signal."""
    path = "data/frost_severity/brazil_coffee.json"
    assert os.path.exists(path), "run scripts.build_frost_severity"
    rec = json.load(open(path))
    assert rec["region_key"] == "brazil_coffee"
    assert rec["worst_year"] == 1994                       # the biggest historical Brazil coffee frost
    assert set(rec["severe_years"]) >= {1994, 2021}        # both catastrophic frosts flagged
    assert 0.45 <= rec["worst_extent"] <= 0.75             # ~60% of the belt froze in 1994
    # discrimination: ordinary winters must NOT saturate — most years well below the severe floor
    normal = [e for e in rec["series"].values() if e < 0.30]
    assert len(normal) >= rec["n_years"] - 4               # only a handful of severe/elevated years
