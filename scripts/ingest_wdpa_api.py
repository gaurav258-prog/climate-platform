"""Load WDPA / WD-OECM protected areas for a targeted set of countries via the Protected Planet API — no
722 MB download, just the countries in your book. Converts each area's GeoJSON to res-8 H3 cells and lands
them in `protected_h3_cell` (same lookup the app already reads), tagged by `--dataset` (wdpa · wdoecm).

Needs a free Protected Planet API token (request at https://api.protectedplanet.net/documentation).

Usage:
    .venv/bin/python -m scripts.ingest_wdpa_api --token $PP_TOKEN --dataset wdpa \
        --countries CIV,IND,VNM,GHA,BRA,IDN,ETH,USA,KEN,AUS,MAR,COL,ARG [--include-oecm] [--buffer-km 1.0]

Runs offline against the API; the app runtime only ever reads the resulting table. Global coverage coexists
with the EU Natura 2000 dataset (the exposure query spans every loaded dataset).
"""
from __future__ import annotations

import argparse
import time
from datetime import date

import h3
import requests
from shapely.geometry import shape
from sqlalchemy import text

from core.db.session import get_session

API = "https://api.protectedplanet.net/v3/protected_areas/search"
VINTAGE = date.today()


def _cells_for_geom(geom, res: int) -> set[str]:
    """Res-`res` H3 cells covering a (multi)polygon. Shapely coords are (lon, lat); h3 wants (lat, lng)."""
    cells: set[str] = set()
    geoms = geom.geoms if geom.geom_type.startswith("Multi") else [geom]
    for g in geoms:
        if g.is_empty or g.geom_type not in ("Polygon",):
            continue
        ext = [(y, x) for x, y in g.exterior.coords]
        holes = [[(y, x) for x, y in ring.coords] for ring in g.interiors]
        try:
            cells.update(h3.polygon_to_cells(h3.LatLngPoly(ext, *holes), res))
        except Exception:
            c = g.representative_point(); cells.add(h3.latlng_to_cell(c.y, c.x, res))
    return cells


def _fetch_country(token: str, iso3: str, oecm: bool) -> list[dict]:
    """All protected areas (with geometry) for one ISO3, paginated."""
    out, page = [], 1
    while True:
        params = {"token": token, "country": iso3, "with_geometry": "true", "per_page": 50, "page": page}
        if oecm:
            params["is_oecm"] = "true"
        r = requests.get(API, params=params, timeout=60)
        r.raise_for_status()
        pas = r.json().get("protected_areas", [])
        if not pas:
            break
        out.extend(pas)
        page += 1
        time.sleep(0.2)      # be polite to the API
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--countries", required=True, help="comma-separated ISO3 codes")
    ap.add_argument("--dataset", default="wdpa")
    ap.add_argument("--include-oecm", action="store_true", help="also pull WD-OECM (other conservation measures)")
    ap.add_argument("--buffer-km", type=float, default=1.0)
    ap.add_argument("--res", type=int, default=8)
    args = ap.parse_args()

    isos = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    seen: dict[str, tuple[float, str | None]] = {}
    for iso in isos:
        pas = _fetch_country(args.token, iso, oecm=args.include_oecm)
        print(f"{iso}: {len(pas)} areas")
        for pa in pas:
            gj = (pa.get("geojson") or {}).get("geometry")
            if not gj:
                continue
            geom = shape(gj)
            ref = str(pa.get("wdpa_id") or pa.get("id") or "")
            for c in _cells_for_geom(geom, args.res):
                seen[c] = (0.0, ref)
            if args.buffer_km and args.buffer_km > 0:
                deg = args.buffer_km / 111.0            # ~km→deg (global approximation, fine for a ~1 km flag)
                for c in _cells_for_geom(geom.buffer(deg), args.res):
                    seen.setdefault(c, (args.buffer_km, ref))

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
