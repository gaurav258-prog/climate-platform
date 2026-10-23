"""Fetch the official XBRL taxonomy packages the validators run on, exactly as the reference data pins them.

    PYTHONPATH=. venv/bin/python -m scripts.fetch_xbrl_packages [--dir DIR] [--publisher eiopa|eba] [--dry-run]

Every file is pinned in the repository's reference data — address, size and SHA-256 — next to what it is used for:
  EIOPA   data/reference/eiopa/s2701_xbrl.<version>.json   'package' and 'deactivations' (S.27.01.01)
  EBA     data/reference/eba/p3esg_xbrlcsv.<version>.json  'packages' (Pillar 3 ESG, the EBA's Pillar 3 data hub)
Nothing else is fetched. Each file lands in DIR/<publisher>/<version>/ (DIR = --dir or XBRL_PACKAGES_DIR), is priced
with a HEAD request first (a size other than the pinned one is refused: the publisher has changed the file, which is
re-verified before use) and is kept only when its SHA-256 is the pinned one. An archive whose pin lists 'extract'
members (the EBA ships its taxonomy as packages inside one zip) has exactly those members unpacked beside it, each
checked against its own pinned SHA-256. Held files are re-checked, not fetched again. The packages are not
redistributed with the repository; the publishers' terms are recorded with each pin ('licence').
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def pins(publisher: str | None = None) -> list[dict]:
    """Every pinned file: {publisher, version, file, url, bytes, sha256, extract}."""
    out = []
    if publisher in (None, "eiopa"):
        for p in sorted(glob.glob(str(ROOT / "data/reference/eiopa/s2701_xbrl.*.json"))):
            m = json.load(open(p))
            for key in ("package", "deactivations"):
                if m.get(key):
                    out.append({"publisher": "eiopa", "version": m["taxonomy_version"], **m[key]})
    if publisher in (None, "eba"):
        for p in sorted(glob.glob(str(ROOT / "data/reference/eba/p3esg_xbrlcsv.*.json"))):
            m = json.load(open(p))
            out += [{"publisher": "eba", "version": m["framework_release"], **pk} for pk in m["packages"]]
    return out


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract(pin: dict, archive: Path) -> list[str]:
    problems = []
    if not pin.get("extract"):
        return problems
    with zipfile.ZipFile(archive) as z:
        for member in pin.get("extract") or []:
            out = archive.parent / Path(member["member"]).name
            if out.exists() and sha256(out) == member["sha256"]:
                continue
            with z.open(member["member"]) as src, open(out, "wb") as dst:
                while chunk := src.read(1 << 20):
                    dst.write(chunk)
            if sha256(out) != member["sha256"]:
                out.unlink()
                problems.append(f"{out.name}: unpacked member's SHA-256 is not the pinned one")
    return problems


def fetch(pin: dict, root: Path, dry_run: bool = False) -> str:
    from scripts.download import download, remote_size
    out = root / pin["publisher"] / pin["version"] / pin["file"]
    if out.exists() and sha256(out) == pin["sha256"]:
        problems = [] if dry_run else _extract(pin, out)
        return "held" if not problems else "failed: " + "; ".join(problems)
    status, size = remote_size(pin["url"])
    if size != pin["bytes"]:
        return f"refused: the server answers {status} with {size} bytes, the pin says {pin['bytes']}"
    if dry_run:
        return f"to fetch ({size:,} bytes)"
    out.parent.mkdir(parents=True, exist_ok=True)
    got = download(pin["url"], out, size)
    if got.startswith("failed"):
        return got
    if sha256(out) != pin["sha256"]:
        out.unlink()
        return "failed: SHA-256 is not the pinned one (file removed)"
    problems = _extract(pin, out)
    return "fetched" if not problems else "failed: " + "; ".join(problems)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", default=os.environ.get("XBRL_PACKAGES_DIR"))
    ap.add_argument("--publisher", choices=("eiopa", "eba"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if not a.dir:
        ap.error("give --dir or set XBRL_PACKAGES_DIR")
    bad = 0
    for pin in pins(a.publisher):
        res = fetch(pin, Path(a.dir).expanduser(), a.dry_run)
        bad += res.startswith(("failed", "refused"))
        print(f"{pin['publisher']}/{pin['version']}/{pin['file']}: {res}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
