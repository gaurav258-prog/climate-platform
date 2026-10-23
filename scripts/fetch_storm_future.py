"""Fetch the STORM Climate Change synthetic tropical-cyclone tracks (the product owner's approval of 2026-10-22; the
archived copy approved 2026-10-23).

Bloemendaal, N. et al., 'STORM Climate Change synthetic tropical cyclone tracks', 4TU.ResearchData, version 1,
doi:10.4121/14237678, CC0: 10,000 synthetic years per climate model — the IBTrACS input of STORM shifted by each of
four high-resolution models' change between 1979–2014 and 2015–2050 under SSP5-8.5 — the same generator as the present
set the storm maps are built from (storm_v4). The record (its file names, sizes and MD5s) is read from figshare's API.

Exactly the approved files, each checked against the size and MD5 the record states; one that differs is refused and
removed. Each file is asked of the publisher first (figshare's file host); when that fails, of the Internet Archive's
capture of the same file on 4TU's own server (data.4tu.nl/file/<dataset>/<file>) — the product owner's decision of
2026-10-23, the publisher's hosts having refused every request since 2026-10-22. The record's MD5 decides either way,
and the URL that served each file is recorded. Every file goes through scripts/download.py (retries, resumes). The files
land in their own folder (data/datasets/storm_v4_future/raw, git-ignored) and are read later only from outside it.

    venv/bin/python -m scripts.fetch_storm_future
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from scripts.download import download

ARTICLE = "https://api.figshare.com/v2/articles/14237678"
APPROVED = {"README.txt": 2458, "ECEARTH.zip": 727358985, "HADGEM.zip": 801314743, "CMCC.zip": 710803350,
            "CNRM.zip": 703841608}
# The Internet Archive's captures of the same files on 4TU's server: (capture timestamp, 4TU file id). Each capture's
# size was read (HEAD) on 2026-10-23; HADGEM's capture of 2025-11-11 05:44:49 is truncated and is not listed.
_4TU = "https://data.4tu.nl/file/98900e17-8e01-4d70-b3b6-ca1a1da2f194"
MIRRORS = {"README.txt": ("20250425060152", "0bb928fe-ac1a-467b-8d05-12c8a7aac77e"),
           "ECEARTH.zip": ("20251111063849", "2eaeb5f6-40f3-4f94-9f9c-ca7aad3237fc"),
           "HADGEM.zip": ("20251111225241", "f35142d6-d858-4874-9a51-2dc08462d45f"),
           "CMCC.zip": ("20251111055037", "bdc3820c-7b7e-41de-8def-792f50b06c49"),
           "CNRM.zip": ("20251226200956", "3b08e6a8-2824-435f-a141-9509a9922cfe")}
OUT = Path(__file__).resolve().parents[1] / "data" / "datasets" / "storm_v4_future"


def mirror_url(name: str) -> str:
    ts, file_id = MIRRORS[name]
    return f"https://web.archive.org/web/{ts}id_/{_4TU}/{file_id}"     # id_: the capture's bytes as served, unaltered


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_one(name: str, size: int, want: str, urls: list[str], raw: Path) -> dict | str:
    """The file from the first URL that serves it whole and with the record's MD5; else why not."""
    out, why = raw / name, []
    for url in urls:
        status = download(url, out, size, attempts=3)
        if status.startswith("failed"):
            why.append(f"{url}: {status}")
            continue
        if md5(out) != want:
            out.unlink()
            why.append(f"{url}: MD5 differs from the record's {want}; removed")
            continue
        return {"status": status, "bytes": size, "md5": want, "url": url}
    return "failed: " + " | ".join(why)


def main() -> int:
    record = requests.get(ARTICLE, timeout=60).json()
    files = {f["name"]: f for f in record["files"]}
    if {n: files.get(n, {}).get("size") for n in APPROVED} != APPROVED:
        print(f"refused: the record's files are not the approved ones: {sorted(files)}")
        return 1
    raw = OUT / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    got = {}
    for name, size in APPROVED.items():
        f = files[name]
        want = f.get("computed_md5") or f.get("supplied_md5")
        got[name] = fetch_one(name, size, want, [f["download_url"], mirror_url(name)], raw)
        print(f"  {name}: {got[name] if isinstance(got[name], str) else got[name]['status'] + ' from ' + got[name]['url']}",
              flush=True)
    (OUT / "provenance.json").write_text(json.dumps({
        "dataset": record["title"], "doi": record["doi"], "version": record["version"],
        "licence": record["license"]["name"], "published": record["published_date"],
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": got}, indent=1))
    failed = [n for n, v in got.items() if isinstance(v, str)]
    print({"fetched": len(got) - len(failed), "failed": failed})
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
