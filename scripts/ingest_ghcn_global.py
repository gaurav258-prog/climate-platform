"""Observed daily extremes 1991–2020 at GLOBAL GHCN-Daily stations (Africa, Asia, Latin America, Oceania).

Same NOAA NCEI access service, same completeness rule (>=330 daily values of TMIN/TMAX/PRCP in a year, >=20 such
years) and same extremes as scripts/ingest_ghcn_extremes.py (its `extremes` is reused unchanged). Output is a JSON
file (data/ghcn_global/extremes.json), not the EU/US table.

Pre-registered selection (fixed before any score is computed): candidates = stations whose inventory shows TMIN, TMAX
and PRCP starting <=1991 and ending >=2020, located (polygon lookup) in one of the 4 target macro-regions; grouped
into 1° boxes; boxes ordered per region by sha1("region:latbox:lonbox"); the first CAP_PER_REGION boxes are taken;
in each box candidates are tried in station-id order (max 5 tries) and the first with >=20 complete years is kept.
4 worker threads, each pausing 0.5 s between requests (NCEI public, no credentials).
Run:  PYTHONPATH=. .venv/bin/python scripts/ingest_ghcn_global.py
"""
from __future__ import annotations

import collections
import hashlib
import json
import time
from pathlib import Path

from ml.validation.regional import macro_region
from scripts.ingest_ghcn_extremes import extremes, fetch

OUT = Path("data/ghcn_global/extremes.json")
REGIONS = ("africa", "asia", "latin_america_caribbean", "oceania")
CAP_PER_REGION = 150
MAX_TRIES = 5


def candidates() -> dict:
    inv: dict = collections.defaultdict(dict)
    for l in open("data/ghcn/ghcnd-inventory.txt"):
        e = l[31:35]
        if e in ("TMIN", "TMAX", "PRCP"):
            inv[l[:11]][e] = (int(l[36:40]), int(l[41:45]), float(l[12:20]), float(l[21:30]))
    names = {l[:11]: l[41:71].strip() for l in open("data/ghcn/ghcnd-stations.txt")}
    boxes: dict = collections.defaultdict(list)
    for sid in sorted(inv):
        d = inv[sid]
        if len(d) < 3 or max(v[0] for v in d.values()) > 1991 or min(v[1] for v in d.values()) < 2020:
            continue
        lat, lon = d["TMAX"][2], d["TMAX"][3]
        r = macro_region(lat, lon)
        if r in REGIONS:
            boxes[(r, int(lat // 1), int(lon // 1))].append((sid, lat, lon, names.get(sid, "")))
    return boxes


def _pick(k, cand):
    for sid, lat, lon, name in cand[:MAX_TRIES]:
        ex = extremes(fetch(sid)); time.sleep(0.5)
        if ex:
            return {"station_id": sid, "name": name, "region": k[0], "latitude": lat, "longitude": lon, **ex}
    return None


def main() -> None:
    from concurrent.futures import ThreadPoolExecutor
    boxes = candidates()
    data = json.load(open(OUT)) if OUT.exists() else {"stations": [], "tried_boxes": []}
    done = set(data["tried_boxes"])
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=4) as pool:
        for reg in REGIONS:
            keys = sorted((k for k in boxes if k[0] == reg), key=lambda k: hashlib.sha1(f"{k[0]}:{k[1]}:{k[2]}".encode()).hexdigest())[:CAP_PER_REGION]
            print(reg, "candidate boxes", len([k for k in boxes if k[0] == reg]), "taken", len(keys), flush=True)
            todo = [k for k in keys if f"{k[0]}:{k[1]}:{k[2]}" not in done]
            for k, st in zip(todo, pool.map(lambda k: _pick(k, boxes[k]), todo)):
                if st:
                    data["stations"].append(st)
                data["tried_boxes"].append(f"{k[0]}:{k[1]}:{k[2]}")
                if len(data["tried_boxes"]) % 20 == 0:
                    OUT.write_text(json.dumps(data)); print(f"  {len(data['tried_boxes'])} boxes, {len(data['stations'])} stations, {time.time()-t0:.0f}s", flush=True)
    OUT.write_text(json.dumps(data))
    print("done", collections.Counter(s["region"] for s in data["stations"]), f"{time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
