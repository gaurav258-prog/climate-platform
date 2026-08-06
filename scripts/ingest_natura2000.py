"""Preprocess a protected-areas GeoPackage into the `protected_h3_cell` lookup (res-8 H3 cells, h3 v4,
matching the app's `h3.latlng_to_cell(lat, lon, 8)` geocoding). Runs offline — no PostGIS needed at runtime;
the app then answers "is this site/plot in or near a protected area?" with a simple indexed membership test.

Dataset-agnostic: works for the EU **Natura 2000** (EEA) file and the global **WDPA** (Protected Planet) file
— it auto-detects the site-id column (SITECODE vs WDPAID) and the country filter (SITECODE prefix vs ISO3).
The `--dataset` tag keeps sources side by side in `protected_h3_cell`, so EU + global coexist.

Usage:
    # EU (Natura 2000):
    .venv/bin/python -m scripts.ingest_natura2000 \
        --gpkg-zip data/natura2000/Natura2000_end2021_rev1_gpkg.zip --dataset natura2000 [--country ES]
    # Global (WDPA):
    .venv/bin/python -m scripts.ingest_natura2000 \
        --gpkg-zip data/wdpa/WDPA_gpkg.zip --dataset wdpa [--country USA] [--buffer-km 1.0] [--res 8]

Needs geopandas + pyogrio (GDAL):  .venv/bin/pip install geopandas pyogrio
This is a heavy one-off job (full-EU load produces ~millions of cells); a --country filter keeps a demo run
fast. The runtime only ever reads the resulting table.
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from datetime import date
from pathlib import Path

import h3
from sqlalchemy import text

from core.db.session import get_session

VINTAGE = date(2021, 12, 31)     # Natura 2000 "end 2021" release


def _find_gpkg(zip_path: Path, workdir: Path) -> Path:
    """Unzip and return the .gpkg inside (Natura 2000 ships one GeoPackage in the zip)."""
    if zip_path.suffix.lower() == ".gpkg":
        return zip_path
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".gpkg")]
        if not names:
            sys.exit("No .gpkg found inside the zip.")
        z.extract(names[0], workdir)
        return workdir / names[0]


def _polygon_layer(gpkg: Path) -> str:
    import pyogrio
    layers = [l[0] for l in pyogrio.list_layers(gpkg)]
    # the polygon layer — Natura 2000 'NaturaSite_polygon', WDPA 'WDPA_poly_…'; fall back to the first
    return next((l for l in layers if "poly" in l.lower()), layers[0])


def _cells_for_geom(geom, res: int) -> set[str]:
    """Res-`res` H3 cells covering a (multi)polygon. Shapely coords are (lon, lat); h3 wants (lat, lng)."""
    cells: set[str] = set()
    geoms = geom.geoms if geom.geom_type.startswith("Multi") else [geom]
    for g in geoms:
        if g.is_empty:
            continue
        ext = [(y, x) for x, y in g.exterior.coords]            # (lat, lng)
        holes = [[(y, x) for x, y in ring.coords] for ring in g.interiors]
        try:
            poly = h3.LatLngPoly(ext, *holes)
            cells.update(h3.polygon_to_cells(poly, res))
        except Exception:
            # tiny/degenerate polygon → index its representative point so it's never silently dropped
            c = g.representative_point()
            cells.add(h3.latlng_to_cell(c.y, c.x, res))
    return cells


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpkg-zip", required=True)
    ap.add_argument("--country", default=None, help="ISO2 filter on SITECODE prefix (e.g. ES) — keeps a demo run small")
    ap.add_argument("--buffer-km", type=float, default=1.0, help="also flag cells within this many km of a site")
    ap.add_argument("--res", type=int, default=8)
    ap.add_argument("--dataset", default="natura2000")
    args = ap.parse_args()

    import geopandas as gpd
    work = Path("data/natura2000")
    work.mkdir(parents=True, exist_ok=True)
    gpkg = _find_gpkg(Path(args.gpkg_zip), work)
    layer = _polygon_layer(gpkg)
    print(f"reading {gpkg.name} · layer {layer}")
    gdf = gpd.read_file(gpkg, layer=layer, engine="pyogrio")

    # site-identifier column (Natura 2000: SITECODE · WDPA: WDPAID/WDPA_PID)
    code_col = next((c for c in gdf.columns if c.upper() in ("SITECODE", "SITE_CODE", "WDPAID", "WDPA_PID", "WDPA_ID")), None)
    # country filter — WDPA carries an ISO3 column (may be multi, ';'-joined for transboundary); Natura 2000
    # encodes the country in the SITECODE prefix (2-letter). Pass ES for Natura 2000, ESP for WDPA.
    iso_col = next((c for c in gdf.columns if c.upper() in ("ISO3", "ISO3_CODE", "PARENT_ISO3", "COUNTRY")), None)
    if args.country:
        cc = args.country.upper()
        if iso_col:
            gdf = gdf[gdf[iso_col].astype(str).str.upper().str.contains(cc, na=False)]
        elif code_col:
            gdf = gdf[gdf[code_col].astype(str).str.upper().str.startswith(cc)]
    print(f"{len(gdf)} sites{' (' + args.country + ')' if args.country else ''} · id col {code_col} · dataset {args.dataset}")

    # WGS84 for H3; add a metric buffer (project to EU LAEA 3035, buffer in metres, back to 4326)
    gdf = gdf.to_crs(4326)
    if args.buffer_km and args.buffer_km > 0:
        buffered = gdf.to_crs(3035).buffer(args.buffer_km * 1000).to_crs(4326)
    else:
        buffered = gdf.geometry

    seen: dict[str, tuple[float, str | None]] = {}     # cell → (within_km, site_ref) keeping the closest (0 = overlap)
    for i, (_, row) in enumerate(gdf.iterrows()):
        site = str(row[code_col]) if code_col else None
        for c in _cells_for_geom(row.geometry, args.res):        # overlap cells → within_km 0
            seen[c] = (0.0, site)
        if args.buffer_km and args.buffer_km > 0:
            for c in _cells_for_geom(buffered.iloc[i], args.res):
                seen.setdefault(c, (args.buffer_km, site))
        if (i + 1) % 500 == 0:
            print(f"  …{i + 1} sites → {len(seen):,} cells")

    print(f"{len(seen):,} protected H3 cells → DB")
    rows = [{"c": c, "r": args.res, "d": args.dataset, "w": w, "s": s, "v": VINTAGE} for c, (w, s) in seen.items()]
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
