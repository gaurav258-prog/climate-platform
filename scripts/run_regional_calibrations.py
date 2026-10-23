"""Regional crop calibrations (calibration_protocol.json 'regional'): build the weather over each crop's area inside the
regions that hold their country's declared regional yields, generate the regional recipes the protocol allows, run them
and propose the runs that would change a publication — one approval request (calibration.review). Nothing publishes
from here. The weather build reads the global ERA5-Land files band by band: run it as its own process, never in the API.

    python -m scripts.run_regional_calibrations --weather --generate --run   # all three, in order
    python -m scripts.run_regional_calibrations --generate --dry-run         # show the recipes, write nothing
"""
from __future__ import annotations

import argparse
import sys

from core.db.session import get_session
from services.calibration import crop_weather, pipeline, regional_specs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weather", action="store_true", help="a weather build of the regional targets")
    ap.add_argument("--generate", action="store_true", help="generate the regional recipes and coverage")
    ap.add_argument("--run", action="store_true", help="run the regional recipes and propose the changes")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    with get_session() as s:
        if a.weather:
            regions = regional_specs.weather_regions(s)
            build_id = crop_weather.build(s, [], [], regions)
            print(f"weather build {build_id}: {sum(len(v) for v in regions.values())} regional targets")
            if not a.dry_run:
                s.commit()
        if a.generate:
            g = regional_specs.generate(s)
            print(f"regional recipes created {g['created']}, retired {g['retired']}; coverage {g['coverage']}")
            for st in g["stale_published"]:
                print(f"  published recipe no longer generated — for a reviewer: {st}")
        if a.run:
            out = pipeline.run(s, regional=True, reason="Regional calibration run (crop-calib-reg-v1)")
            for r in sorted(out["runs"], key=lambda r: (r["commodity"], r["region"])):
                print(f"  {r['commodity'][:12]:12} {r['region']:6} {r['outcome']:13} r2_oos={r['r2_oos']}"
                      f"  downside={'pass' if r['downside_pass'] else 'held'}")
            p = out["proposal"]
            print(f"runs {len(out['runs'])}; proposed for review: {p['runs']} run(s), request {p['approval_request_id']}"
                  if p else f"runs {len(out['runs'])}; nothing to propose")
        if a.dry_run:
            s.rollback()
            print("dry run — nothing written")
        else:
            s.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
