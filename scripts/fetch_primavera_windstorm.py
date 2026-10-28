"""Fetch the PRIMAVERA European winter windstorm event set (the product owner's approval of 2026-10-25).

Lockwood, J. et al., 'PRIMAVERA European winter windstorm event set', Zenodo, version 1, doi:10.5281/zenodo.6492182,
Open Government Licence v3.0: the 72-hour maximum 3-second gust footprints of every winter (October–March) storm
tracked in 21 high-resolution climate-model runs forced with observed sea temperatures, winters 1950/51–2013/14
('approximately 1300 years of windstorm data'), plus the same footprints from the ERA5 reanalysis and the record's
documentation. The record (its file names, sizes and MD5s) is read from Zenodo's API.

Exactly the approved files (23, 13,629,123,071 bytes), each checked against the size and MD5 the record states; one
that differs is refused and removed. Every file goes through scripts/download.py (retries, resumes). The files land in
their own folder (data/datasets/primavera_windstorm/raw, git-ignored) and are read later only from outside it.

    venv/bin/python -m scripts.fetch_primavera_windstorm
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from scripts.download import download

RECORD = "https://zenodo.org/api/records/6492182"
APPROVED_FILES, APPROVED_BYTES = 23, 13_629_123_071
OUT = Path(__file__).resolve().parents[1] / "data" / "datasets" / "primavera_windstorm"


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    record = requests.get(RECORD, timeout=60).json()
    files = record["files"]
    if len(files) != APPROVED_FILES or sum(f["size"] for f in files) != APPROVED_BYTES:
        print(f"refused: the record holds {len(files)} files of {sum(f['size'] for f in files)} bytes, "
              f"not the approved {APPROVED_FILES} of {APPROVED_BYTES}")
        return 1
    raw = OUT / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    got = {}
    for f in sorted(files, key=lambda f: f["size"]):
        name, size = f["key"], f["size"]
        want = f["checksum"].removeprefix("md5:")
        out = raw / name
        status = download(f["links"]["self"], out, size, attempts=5)
        if not status.startswith("failed") and md5(out) != want:
            out.unlink()
            status = f"failed: MD5 differs from the record's {want}; removed"
        got[name] = {"status": status, "bytes": size, "md5": want, "url": f["links"]["self"]}
        print(f"  {name}: {status}", flush=True)
    m = record["metadata"]
    (OUT / "provenance.json").write_text(json.dumps({
        "dataset": m["title"], "doi": m["doi"], "version": m.get("version"), "licence": m["license"]["id"],
        "published": m["publication_date"], "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": got}, indent=1))
    failed = [n for n, v in got.items() if v["status"].startswith("failed")]
    print({"fetched": len(got) - len(failed), "failed": failed})
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
