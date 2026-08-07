"""Load protected areas from OpenStreetMap (Overpass API) into `protected_h3_cell`, tagged `osm` — a FREE,
commercially-usable (ODbL + attribution) global coverage layer for the non-EU book, where the authoritative
WDPA is licence-gated. Per-country, no account, no bulk download. Community-sourced (uneven coverage) — an
honest screening layer, not an authoritative agency feed; labelled as such in-product.

Usage:
    .venv/bin/python -m scripts.ingest_osm_protected \
        --countries CI,IN,VN,GH,BR,ID,ET,US,KE,AU,MA,CO,AR [--buffer-km 1.0] [--res 8]

Attribution required: "© OpenStreetMap contributors (ODbL)".
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import date

import h3
import osm2geojson
from shapely.geometry import shape
from sqlalchemy import text

from core.db.session import get_session

# public Overpass instances (fall back to the mirror if the first rate-limits)
ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
UA = {"User-Agent": "Tellumen climate-platform / protected-area screening (ESRS E4)"}
# OSM tagging for protected areas — the common schemes
TAGS = [("boundary", "protected_area"), ("leisure", "nature_reserve"), ("boundary", "national_park")]
VINTAGE = date.today()


def _cells_for_geom(geom, res: int) -> set[str]:
    cells: set[str] = set()
    geoms = geom.geoms if geom.geom_type.startswith("Multi") else [geom]
    for g in geoms:
        if g.is_empty or g.geom_type != "Polygon":
            continue
        ext = [(y, x) for x, y in g.exterior.coords]
        holes = [[(y, x) for x, y in ring.coords] for ring in g.interiors]
        try:
            cells.update(h3.polygon_to_cells(h3.LatLngPoly(ext, *holes), res))
        except Exception:
            c = g.representative_point(); cells.add(h3.latlng_to_cell(c.y, c.x, res))
    return cells


def _query_country(iso2: str) -> dict:
    # `out geom;` returns geometry inline (no heavy node dump). Fetched via curl — the venv Python's LibreSSL
    # is unreliable for HTTPS to Overpass, curl uses the system TLS.
    parts = "".join(f'way["{k}"="{v}"](area.a);relation["{k}"="{v}"](area.a);' for k, v in TAGS)
    q = (f'[out:json][timeout:300];area["ISO3166-1"="{iso2}"][admin_level=2]->.a;({parts});out geom;')
    last = None
    for ep in ENDPOINTS:
        for attempt in range(3):
            p = subprocess.run(["curl", "-sS", "-m", "330", "-G", ep, "-H", "User-Agent: " + UA["User-Agent"],
                                "--data-urlencode", "data=" + q], capture_output=True, text=True)
            out = (p.stdout or "").strip()
            if p.returncode == 0 and out.startswith("{"):
                try:
                    return json.loads(out)
                except Exception as e:      # noqa: BLE001
                    last = e
            else:
                last = (p.stderr or out)[:80]
            time.sleep(4 * (attempt + 1))
    raise RuntimeError(str(last)[:100])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", required=True, help="comma-separated ISO2 codes (OSM ISO3166-1)")
    ap.add_argument("--buffer-km", type=float, default=1.0)
    ap.add_argument("--res", type=int, default=8)
    ap.add_argument("--dataset", default="osm")
    args = ap.parse_args()

    isos = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    seen: dict[str, tuple[float, str | None]] = {}
    deg = (args.buffer_km / 111.0) if args.buffer_km and args.buffer_km > 0 else 0
    for iso in isos:
        try:
            gj = osm2geojson.json2geojson(_query_country(iso))
        except Exception as e:
            print(f"{iso}: SKIPPED ({type(e).__name__}: {str(e)[:60]})")
            continue
        feats = [f for f in gj.get("features", []) if (f.get("geometry") or {}).get("type") in ("Polygon", "MultiPolygon")]
        n0 = len(seen)
        for f in feats:
            geom = shape(f["geometry"])
            ref = str((f.get("properties") or {}).get("id") or "")
            for c in _cells_for_geom(geom, args.res):
                seen[c] = (0.0, ref)
            if deg:
                for c in _cells_for_geom(geom.buffer(deg), args.res):
                    seen.setdefault(c, (args.buffer_km, ref))
        print(f"{iso}: {len(feats)} protected areas → +{len(seen) - n0:,} cells")
        time.sleep(1)      # be polite to the public Overpass instance

    rows = [{"c": c, "r": args.res, "d": args.dataset, "w": w, "s": s, "v": VINTAGE} for c, (w, s) in seen.items()]
    print(f"{len(rows):,} protected H3 cells ({args.dataset}) → DB")
    with get_session() as ses:
        ses.execute(text("DELETE FROM protected_h3_cell WHERE dataset = :d"), {"d": args.dataset})
        for j in range(0, len(rows), 5000):
            ses.execute(text("""
                INSERT INTO protected_h3_cell (h3_cell, h3_res, dataset, within_km, site_ref, data_vintage)
                VALUES (:c, :r, :d, :w, :s, :v)
                ON CONFLICT (h3_cell, dataset) DO UPDATE SET within_km = LEAST(protected_h3_cell.within_km, EXCLUDED.within_km)
            """), rows[j:j + 5000])
        ses.commit()
    print("done.")


if __name__ == "__main__":
    main()
