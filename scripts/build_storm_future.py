"""Build the STORM Climate Change event set (storm_cc, data/reference/event_sets.json) from its fetched archives: each
model's archive is checked against the MD5 its record states (data/datasets/storm_v4_future/provenance.json, written by
scripts/fetch_storm_future.py), only its named track files are taken out — flat, into tracks/<model>/, never a path the
archive chooses — and they are compacted into per-basin arrays by the same code as the present set
(services.loss.storm_events.compact), each array's size and sha-256 recorded in data/reference/supply_datasets.json.

Usage: venv/bin/python -m scripts.build_storm_future [--model EC-Earth3P-HR]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "datasets" / "storm_v4_future"


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract(model: str, archive: str, E: dict) -> int:
    prov = json.loads((BASE / "provenance.json").read_text())["files"][archive]
    if isinstance(prov, str):
        raise SystemExit(f"{archive}: not fetched ({prov})")
    z = BASE / "raw" / archive
    if md5(z) != prov["md5"]:
        raise SystemExit(f"{archive}: differs from the MD5 the record states — refused")
    want = {E["files"]["pattern"].format(model=model, basin=b, index=i)
            for b in E["basins"] for i in range(E["files"]["per_basin"])}
    out = ROOT / E["files"]["dir"].format(model=model)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(z) as zf:
        names = {Path(m).name: m for m in zf.namelist() if not m.endswith("/")}
        missing = want - set(names)
        if missing:
            raise SystemExit(f"{archive}: lacks {len(missing)} of its track files, e.g. {sorted(missing)[0]}")
        for name in sorted(want):
            with zf.open(names[name]) as src, (out / name).open("wb") as dst:
                for chunk in iter(lambda: src.read(1 << 20), b""):
                    dst.write(chunk)
            n += 1
    return n


def main() -> int:
    from services.loss import registry, storm_events
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    a = ap.parse_args()
    E = registry.event_sets()["storm_cc"]
    for model, archive in E["models"].items():
        if a.model and model != a.model:
            continue
        n = extract(model, archive, E)
        rec = storm_events.compact("storm_cc", model)
        print(f"{model}: {n} track files; " + ", ".join(f"{b} {v['track_points']:,} points" for b, v in rec.items()),
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
