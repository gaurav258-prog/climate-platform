"""Stage a reviewed yield source's latest data for review — nothing lands from here (E153).

Any source of services.reference.yield_sources (faostat, eurostat, usda_fas …): download, read, compare with the store,
stage as a release; it lands only when approved on the operator console (Reference data) as the Approvers policy states.

    python -m scripts.stage_yield_release --source usda_fas            # fetch and stage
    python -m scripts.stage_yield_release --source usda_fas --dry-run  # show the difference, stage nothing
    python -m scripts.stage_yield_release --source faostat --file <zip>   # a file already on disk
"""
from __future__ import annotations

import argparse
import json
import sys

from core.db.session import get_session
from services.reference import crop_releases as R
from services.reference.yield_sources import _BUILDERS, get


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, choices=sorted(_BUILDERS))
    ap.add_argument("--file", help="the publisher's data already on disk (else downloaded)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    ys = get(a.source)
    data = open(a.file, "rb").read() if a.file else ys.download()
    if not a.file:
        print(f"raw data kept at {R.keep_raw(ys, data)} (re-read with --file if needed)")
    with get_session() as s:
        out = R.stage(s, data, source=ys)
        print(json.dumps({k: v for k, v in out.items() if k != "summary"}, indent=1))
        sm = out.get("summary") or {}
        if sm:
            print(f"rows {sm['rows_in_file']}: added {sm['added']}, revised {sm['revised']}, recomputed {sm['recomputed']}, "
                  f"unchanged {sm['unchanged']}; held but not in the data {sm['held_not_in_file']}; reading changed since "
                  f"the last landed release: {sm['reader_changed_since_last_landed']}; calibrations that may be affected: "
                  f"{len(sm['calibrations_may_be_affected'])}")
        if a.dry_run:
            s.rollback()
            print("dry run — nothing staged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
