"""The present-day check (loss_protocol.json, projection_present_day_check): every asset location is counted once, in the
category the two sources put it — a JRC cell with no land is its own category, never folded into 'dry'. Rolled back."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from services.loss import projection_check, registry

pytestmark = pytest.mark.integration


def _row(s, layer, version, lat, rp, frac, variant):
    s.execute(text("""INSERT INTO hazard_intensity_samples (layer_key, layer_version, latitude, longitude, h3_cell, rp_years,
                      status, value, cell_fraction, cell_mean, scenario, period, climate_model)
                      VALUES (:k, :v, :la, 1.5, 'test', :rp, 'sampled', 0, :f, :m, :s, :p, :cm)"""),
              {"k": layer, "v": version, "la": lat, "rp": rp, "f": frac, "m": None if frac is None else 0.0, **variant})


def test_every_location_lands_in_exactly_one_category(session_rolled_back):
    s = session_rolled_back
    A, J = registry.layer("aqueduct_river_flood"), registry.layer("jrc_river_flood")
    present = {"s": A["present"]["scenario"], "p": A["present"]["year"], "cm": A["present"]["model"]}
    before = projection_check.agreement(s)
    for lat, jf, af in ((-77.1, None, 1.0), (-77.2, 0.4, 0.0), (-77.3, 0.0, 0.0), (-77.4, 0.0, 1.0)):
        _row(s, "jrc_river_flood", J["version"], lat, 100, jf, {"s": "present", "p": "present", "cm": ""})
        _row(s, "aqueduct_river_flood", A["version"], lat, 100, af, present)
    after = projection_check.agreement(s)
    delta = {k: after[k] - before[k] for k in ("locations", "jrc_no_land_in_cell", "both_wet", "both_dry",
                                               "jrc_wet_only", "aqueduct_wet_only")}
    assert delta == {"locations": 4, "jrc_no_land_in_cell": 1, "both_wet": 0, "both_dry": 1, "jrc_wet_only": 1,
                     "aqueduct_wet_only": 1}
    parts = after["jrc_no_land_in_cell"] + after["both_wet"] + after["both_dry"] + after["jrc_wet_only"] + after["aqueduct_wet_only"]
    assert parts == after["locations"]
