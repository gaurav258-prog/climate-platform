"""Run the curve tests on NFIP claims (data/reference/loss_protocol.json): published_curve_test_commercial (North
America commercial, registered 2026-10-23), the correction of published_curve_test (North America residential,
corrected 2026-10-23, E322) and the measured family's rebuild under measured_curves 'countries' (E322). Each result is
recorded on its curve (services.loss.published_test.record) or in its family file (services.loss.measured.write); a
result replaced for E322 is kept under 'superseded'.

Usage: PYTHONPATH=. venv/bin/python -m scripts.run_curve_claims_tests [--only commercial|residential|measured]
"""
from __future__ import annotations

import argparse

from services.loss import measured, published_test

E322 = ("E322: it read claims outside the curve's countries — US outlying areas (Puerto Rico, the US Virgin Islands, "
        "Guam, American Samoa, the Northern Mariana Islands) and claims with no state")
STEPS = ("commercial", "residential", "measured")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=STEPS, action="append", help="run only these steps (default: all three)")
    steps = ap.parse_args().only or list(STEPS)
    keys = ("events_tested", "events_within_tolerance", "median_abs_error", "band_coverage", "passed")
    if "commercial" in steps:
        r = published_test.test("jrc_huizinga_2017", "jrc_huizinga_2017:commercial:021", "published_curve_test_commercial")
        published_test.record("jrc_huizinga_2017", "jrc_huizinga_2017:commercial:021", r)
        print("commercial:021", {k: r[k] for k in keys}, r["set_aside"])
    if "residential" in steps:
        r = published_test.test("jrc_huizinga_2017", "jrc_huizinga_2017:residential:021", "published_curve_test")
        published_test.record("jrc_huizinga_2017", "jrc_huizinga_2017:residential:021", r, supersedes_because=E322)
        print("residential:021", {k: r[k] for k in keys}, r["set_aside"])
    if "measured" in steps:
        fam = measured.write(supersedes_because=E322)
        print("nfip_measured", {k: fam["test"][k] for k in keys}, fam["derivation"]["set_aside"])


if __name__ == "__main__":
    main()
