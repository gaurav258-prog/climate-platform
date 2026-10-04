"""Add a calibration recipe for a crop × origin (a named weather box) and run it through the calibration pipeline
(E162) — the run is recorded with its ledger entry and, if it would change a publication, proposed for review. The
recipe is fixed before it is fitted: say why in --basis (the season and SPEI window from the crop's agronomy, never the
window that fitted best).

    python -m scripts.fit_ranged_crop --commodity "Olive oil" --origin ES --region spain_olive --driver drought \
        --spei-scale 6 --season 4,5,6,7,8 --basis "olive: winter-spring water balance fills the fruit (agronomy …)"
"""
from __future__ import annotations

import argparse
import sys

from core.db.session import get_session
from ml.features.crop_registry import is_alternate_bearing
from services.calibration import publish, runner, specs
from services.calibration.gates import protocol
from services.intelligence.supply_cogs import RANGED_PUBLISH_FLOOR

MIN_R2 = RANGED_PUBLISH_FLOOR          # the publish floor — one constant (tests/integration/test_r2_floor_parity.py)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commodity", required=True)
    ap.add_argument("--origin", required=True)
    ap.add_argument("--region", required=True)
    ap.add_argument("--driver", default="drought", choices=("drought", "heat", "soil_water"))
    ap.add_argument("--spei-scale", type=int, default=6)
    ap.add_argument("--season", required=True)
    ap.add_argument("--source", default="FAOSTAT QCL bulk")
    ap.add_argument("--basis", required=True, help="why this recipe (cited agronomy), at least 20 characters")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if len(a.basis.strip()) < 20:
        print("--basis must say why this recipe (at least 20 characters)")
        return 2
    with get_session() as s:
        sid = specs.create(s, commodity=a.commodity, origin=a.origin, yield_source=a.source, driver=a.driver,
                           weather_kind="box", weather_key=a.region, season_months=[int(m) for m in a.season.split(",")],
                           spei_scale=a.spei_scale, allow_cycle=is_alternate_bearing(a.commodity),
                           basis=a.basis.strip(), protocol=protocol()["protocol"])
        r = runner.run(s, runner.spec(s, sid))
        print(f"{a.commodity}/{a.origin} {a.driver}: {r['outcome']} r2_oos={r['r2_oos']} "
              f"downside={'pass' if r['downside_pass'] else 'held'} upside={'pass' if r['upside_pass'] else 'held'}")
        p = publish.propose(s, [r["run_id"]], f"New recipe: {a.basis.strip()}")
        print(f"proposed for review: request {p['approval_request_id']}" if p else "nothing to propose")
        if a.dry_run:
            s.rollback()
            print("dry run — nothing written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
