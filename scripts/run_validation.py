"""Run the validation/backtesting framework — records an immutable, provenanced result per validator.

    python -m scripts.run_validation                 # run every registered validator
    python -m scripts.run_validation seismic storm   # run specific ones

Each run writes one row to validation_run (audit-grade, append-only) with its skill metrics, grade and
gate verdict. Import the validators package to register them; new hazards register themselves on import.
"""
from __future__ import annotations

import sys

from core.db.session import get_session
import services.validation.validators.near_field_events  # noqa: F401 — registers seismic
import services.validation.validators.storm_severity     # noqa: F401 — registers storm (severity)
import services.validation.validators.agri_crop          # noqa: F401 — registers agri_drought/heat/crop_shock
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
