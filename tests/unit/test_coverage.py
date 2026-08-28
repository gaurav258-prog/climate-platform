"""Coverage summariser — the honest standing + on-demand picture (pure, no DB)."""
from services.intelligence.coverage import ON_DEMAND_HAZARDS, summarize_coverage


def test_summary_reports_standing_and_on_demand():
    per_hazard = [{"hazard": "flood", "cells": 79428}, {"hazard": "seismic", "cells": 9568},
                  {"hazard": "pollution", "cells": 218}]
    s = summarize_coverage(per_hazard, resolutions=[8], scenarios=["baseline", "disorderly_2c"],
                           horizons=["current", "2050"])
    assert s["standing"]["n_cells_max_hazard"] == 79428
    assert s["standing"]["n_hazards"] == 3
    assert s["standing"]["per_hazard"][0]["hazard"] == "flood"       # sorted desc
    assert "pollution" in s["standing"]["thin_layers"]               # < 1000 flagged
    assert "flood" not in s["standing"]["thin_layers"]
    assert s["on_demand"]["global"] is True
    assert s["on_demand"]["hazards_on_demand"] == len(ON_DEMAND_HAZARDS)
