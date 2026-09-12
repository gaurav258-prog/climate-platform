"""Run the validation/backtesting framework — records an immutable, provenanced result per validator.

    python -m scripts.run_validation                 # run every registered validator
    python -m scripts.run_validation seismic storm   # run specific ones

Each run writes one row to validation_run (audit-grade, append-only) with its skill metrics, grade and
gate verdict. Import the validators package to register them; new hazards register themselves on import.
"""
from __future__ import annotations

import sys

import services.validation.validators.agri_crop  # noqa: F401 — registers agri_drought/heat/crop_shock
import services.validation.validators.agri_yield  # noqa: F401 — registers agri_yield_* (ERA5 vs observed yield)
import services.validation.validators.avalanche_slf  # noqa: F401 — registers avalanche_slf (SLF accidents, Swiss Alps)
import services.validation.validators.coastal_erosion_shoreline  # noqa: F401 — registers coastal_erosion_shoreline (Landsat-observed shoreline change)
import services.validation.validators.coastal_gauges  # noqa: F401 — registers coastal_ewl_holdout/logo, coastal_score_coops
import services.validation.validators.flood_jrc  # noqa: F401 — registers flood_jrc_ems
import services.validation.validators.near_field_events  # noqa: F401 — registers seismic
import services.validation.validators.station_extremes  # noqa: F401 — registers cold_wave/heat_chronic/heavy_precip station tests
import services.validation.validators.storm_holdout  # noqa: F401 — registers storm_oos (temporal holdout)
import services.validation.validators.storm_severity  # noqa: F401 — registers storm (severity)
import services.validation.validators.subsidence_egms  # noqa: F401 — registers subsidence_egms (InSAR)
import services.validation.validators.subsidence_egms_holdout  # noqa: F401 — registers subsidence_egms_holdout (v2, in time)
import services.validation.validators.subsidence_gnss  # noqa: F401 — registers subsidence_gnss[_us/_eu]
import services.validation.validators.temporal_holdout  # noqa: F401 — registers seismic_oos (temporal holdout)
import services.validation.validators.water_stress_grace  # noqa: F401 — registers water_stress_grace (GRACE observed storage trend)
import services.validation.validators.windstorm_noaa  # noqa: F401 — registers windstorm_noaa (synoptic field vs NOAA Storm Events)
from core.db.session import get_session
from services.validation import engine


def main() -> int:
    keys = sys.argv[1:] or sorted(engine.REGISTRY)
    with get_session() as s:
        for key in keys:
            if key not in engine.REGISTRY:
                print(f"  ! no validator '{key}' (have: {sorted(engine.REGISTRY)})")
                continue
            r = engine.run_validation(s, key, actor="scripts.run_validation")
            m = r["metrics"]
            skill = (f"r2_oos={m.get('r2_oos')}" if r["kind"] == "regression"
                     else f"spearman={m.get('spearman')}")
            if not m.get("applicable", True):
                skill += f"  [not testable: {m.get('applicability_reason')}]"
            print(f"  {r['hazard']:>10} · {r['grade']:>12} · gate {'PASS' if r['passed_gate'] else 'FAIL'} "
                  f"· n={r['n']} · {skill} · {r['method']} · {r['target_source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
