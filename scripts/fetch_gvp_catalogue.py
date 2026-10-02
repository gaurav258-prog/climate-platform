"""Smithsonian GVP — global Holocene volcano catalogue (feed 'volcanic_gvp').

Lands the global volcano catalogue from the Smithsonian Global Volcanism
Program "Volcanoes of the World" GeoServer WFS (the same authoritative source scripts/ingest_gvp_volcanic.py
uses for the curated per-volcano event rows):

  * GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes  — every Holocene volcano (~1,200): number, name, country,
                                                     type, lat/lon, last eruption year
  * GVP-VOTW:Smithsonian_VOTW_Holocene_Eruptions  — every catalogued eruption (~11,000): VEI, dates, evidence

Per volcano we keep the fields the any-address scorer (ml/scoring/volcanic_point.py) needs and nothing else:
location, type, last eruption year, and the eruption-history aggregates that size the hazard footprint
(max VEI of CONFIRMED eruptions over the Holocene / since 1900, eruption counts). Numbers are copied from GVP,
never inferred; a volcano whose eruptions carry no VEI gets max_vei = null and the scorer says so.

Two copies (core/live_data.py, E114): the committed snapshot data/reference/gvp_holocene_volcanoes.json is the
versioned reference, changed only by --promote; a refresh writes the live copy (<live>/reference/…, gitignored), which
the scorer reads in preference to the snapshot.

Usage:  PYTHONPATH=. venv/bin/python scripts/fetch_gvp_catalogue.py            # refresh the live copy
        PYTHONPATH=. venv/bin/python scripts/fetch_gvp_catalogue.py --promote  # live copy → committed snapshot
Also wired as the refresh hook of feed 'volcanic_gvp' (services/data/feeds.py) so the scheduler re-lands it.
GVP sits behind Cloudflare: a browser-like User-Agent is required (a bare python-requests UA is 403'd).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from core import live_data

GVP_WFS = "https://webservices.volcano.si.edu/geoserver/GVP-VOTW/wfs"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TellumenClimatePlatform/1.0)"}
LAYER_VOLCANOES = "GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes"
LAYER_ERUPTIONS = "GVP-VOTW:Smithsonian_VOTW_Holocene_Eruptions"
SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "data" / "reference" / "gvp_holocene_volcanoes.json"

# The GVP GeoServer occasionally drops the connection outright (no HTTP response at all — not a 403/5xx,
# just a closed socket) rather than rejecting the request; a bare requests.exceptions.ConnectionError from a
# transient edge/rate-limit blip shouldn't kill a whole scheduled refresh. Retry with backoff before giving
# up; a genuinely dead endpoint (or a real 4xx/5xx after connecting) still surfaces as 'failed' as before.
_RETRY_ATTEMPTS = 4
_RETRY_BACKOFF_S = (2, 4, 8)


def _wfs_all(type_name: str, timeout: int = 180) -> list[dict]:
    last_err: Exception | None = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            r = requests.get(GVP_WFS, params={
                "service": "WFS", "version": "2.0.0", "request": "GetFeature",
                "typeName": type_name, "outputFormat": "application/json",
            }, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            feats = r.json().get("features", [])
            if not feats:
                raise RuntimeError(f"GVP WFS returned no features for {type_name}")
            return feats
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_err = e
            if attempt < _RETRY_ATTEMPTS - 1:
                time.sleep(_RETRY_BACKOFF_S[attempt])
    raise RuntimeError(f"GVP WFS unreachable for {type_name} after {_RETRY_ATTEMPTS} attempts: {last_err}")


def _vei(p: dict) -> float | None:
    v = p.get("ExplosivityIndexMax")
    return float(v) if v is not None else None


def build_catalogue(volcanoes: list[dict], eruptions: list[dict]) -> dict:
    """Pure aggregation (testable without network): GeoJSON features → catalogue dict."""
    agg: dict[int, dict] = {}
    for f in eruptions:
        p = f["properties"]
        if p.get("Activity_Type") != "Confirmed Eruption":
            continue  # uncertain / discredited eruptions do not size a hazard footprint
        n = int(p["Volcano_Number"])
        a = agg.setdefault(n, {"n_confirmed": 0, "n_since_1900": 0, "max_vei": None, "max_vei_since_1900": None})
        a["n_confirmed"] += 1
        vei, yr = _vei(p), p.get("StartDateYear")
        if vei is not None and (a["max_vei"] is None or vei > a["max_vei"]):
            a["max_vei"] = vei
        if yr is not None and int(yr) >= 1900:
            a["n_since_1900"] += 1
            if vei is not None and (a["max_vei_since_1900"] is None or vei > a["max_vei_since_1900"]):
                a["max_vei_since_1900"] = vei

    rows = []
    for f in volcanoes:
        p, g = f["properties"], f.get("geometry") or {}
        coords = g.get("coordinates") or [None, None]
        if coords[0] is None or coords[1] is None:
            continue
        n = int(p["Volcano_Number"])
        a = agg.get(n, {})
        rows.append({
            "volcano_number": n, "name": p.get("Volcano_Name"), "country": p.get("Country"),
            "region": p.get("Region"), "type": p.get("Primary_Volcano_Type"),
            "lat": round(float(coords[1]), 4), "lon": round(float(coords[0]), 4),
            "last_eruption_year": p.get("Last_Eruption_Year"),
            "n_confirmed_eruptions": a.get("n_confirmed", 0),
            "n_eruptions_since_1900": a.get("n_since_1900", 0),
            "max_vei": a.get("max_vei"), "max_vei_since_1900": a.get("max_vei_since_1900"),
        })
    rows.sort(key=lambda r: r["volcano_number"])
    return {
        "source": "Smithsonian Institution, Global Volcanism Program — Volcanoes of the World (Holocene), GeoServer WFS",
        "layers": [LAYER_VOLCANOES, LAYER_ERUPTIONS],
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_volcanoes": len(rows), "n_eruptions_total": len(eruptions),
        "n_eruptions_confirmed": sum(a["n_confirmed"] for a in agg.values()),
        "volcanoes": rows,
    }


def _data(cat: dict) -> dict:
    """The catalogue without its fetch time — what decides whether anything actually changed."""
    return {k: v for k, v in cat.items() if k != "fetched_at"}


def refresh(snapshot: Path = SNAPSHOT_PATH) -> dict:
    """Fetch both layers and land the catalogue as the LIVE copy of `snapshot` — only when its data differs from the
    copy readers use now (the live copy, else the committed snapshot). Never writes the committed snapshot (E114).
    Raises on any source failure: the feed monitor must show 'failed', never replace a good catalogue with a partial one.

    `fetched_at` is when THIS VERSION of the data was first fetched (volcanic scores cite it as their catalogue
    version). A check that finds the same data writes nothing: when the feed was last checked lives in the feed
    monitor's own log (feed_refresh_log), not in a file."""
    cat = build_catalogue(_wfs_all(LAYER_VOLCANOES), _wfs_all(LAYER_ERUPTIONS))
    if cat["n_volcanoes"] < 1000:  # GVP lists ~1,200 Holocene volcanoes; far fewer means a truncated response
        raise RuntimeError(f"GVP catalogue looks truncated: {cat['n_volcanoes']} volcanoes")
    current_path = live_data.prefer_live(snapshot)
    if current_path.exists():
        current = json.loads(current_path.read_text())
        if _data(current) == _data(cat):
            return {**current, "changed": False, "path": str(current_path)}
    out = live_data.write_live(snapshot, json.dumps(cat, separators=(",", ":")))
    return {**cat, "changed": True, "path": str(out)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--promote", action="store_true",
                    help="copy the live catalogue over the committed snapshot (a deliberate, separately committed change)")
    if ap.parse_args().promote:
        print(f"promoted {live_data.live_path(SNAPSHOT_PATH)} -> {live_data.promote(SNAPSHOT_PATH)}")
        return 0
    cat = refresh()
    print(f"{'wrote' if cat['changed'] else 'unchanged (not rewritten)'} {cat['path']}: {cat['n_volcanoes']} volcanoes, "
          f"{cat['n_eruptions_confirmed']} confirmed eruptions (of {cat['n_eruptions_total']} catalogued)")
    with_vei = sum(1 for v in cat["volcanoes"] if v["max_vei"] is not None)
    print(f"  {with_vei} volcanoes carry a confirmed-eruption VEI; {cat['n_volcanoes'] - with_vei} do not")
    return 0


if __name__ == "__main__":
    sys.exit(main())
