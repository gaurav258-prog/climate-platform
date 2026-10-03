"""Stage a FAOSTAT crop-production file for review — it never lands from here (E148).

The file is read by services.reference.faostat_crops (mapping: data/reference/faostat_crops.json) and staged by
services.reference.crop_releases with its difference against the store; two platform operators then review it on the
operator console (Reference data) and only their approval writes crop_yield_observations. The scheduled feed
'crop_production_faostat' does the same monthly; this script is for a file already on disk (or a forced download).

    python -m scripts.ingest_crop_yield_faostat --file data/faostat/Production_Crops_Livestock_E_All_Data_(Normalized).zip
    python -m scripts.ingest_crop_yield_faostat --download        # fetch the publisher's file now, then stage it
    python -m scripts.ingest_crop_yield_faostat --file … --dry-run  # show the difference, stage nothing
"""
from __future__ import annotations

import argparse
import json
import sys

from core.db.session import get_session
from services.reference import crop_releases as R
from services.reference import faostat_crops as F


def main() -> int:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="the publisher's zip, already on disk")
    src.add_argument("--download", action="store_true", help="fetch the publisher's file now")
    ap.add_argument("--dry-run", action="store_true", help="show the difference; stage nothing")
    a = ap.parse_args()
    data = F.download() if a.download else open(a.file, "rb").read()
    with get_session() as s:
        out = R.stage(s, data)
        print(json.dumps({k: v for k, v in out.items() if k != "summary"}, indent=1))
        sm = out.get("summary") or {}
        if sm:
            print(f"rows in file {sm['rows_in_file']}: added {sm['added']}, revised {sm['revised']}, recomputed {sm['recomputed']}, "
                  f"unchanged {sm['unchanged']}; held but not in the file {sm['held_not_in_file']}; "
                  f"calibrations that may be affected: {len(sm['calibrations_may_be_affected'])}")
        if a.dry_run:
            s.rollback()
            print("dry run — nothing staged")
            return 0
    print("staged for review — land it from the operator console (Reference data); nothing was written to the store")
    return 0


if __name__ == "__main__":
    sys.exit(main())
