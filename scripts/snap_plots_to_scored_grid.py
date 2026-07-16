"""Snap sourcing plots onto the scored grid for their crop's CALIBRATED DRIVER hazard.

WHY THIS EXISTS. A plot's h3_cell is the key we score on. Our climatological models are
computed on a sampled grid (ERA5-Land is ~9 km; we score a belt of representative cells),
so a plot's own res-8 cell is frequently not one of the scored cells. Unless the plot is
snapped onto a scored cell, its driver hazard reads as "not scored" and — correctly, under
the publish gate — its commodity's € is withheld.

This used to live as a hardcoded plot list inside scripts/score_cocoa_heat.py. That is not
scalable and it silently rots: re-seeding the demo reset the Ghana cocoa plot's h3_cell and
nothing re-snapped it, so Ghana (half the cocoa spend, ~15% of world cocoa) went unscored.
Under the old engine that was invisible — the model just fell back to the next-worst hazard.

So: snapping is keyed on sc_commodity_calibration.hazard_driver — a plot is snapped onto the
nearest cell that is actually scored for THE HAZARD ITS CROP IS CALIBRATED AGAINST, which is
the only hazard that can produce a publishable number for it.

Honest bound: we never snap beyond --max-km (default 25 km, comfortably inside one ERA5-Land
pixel, so the climate signal is the same). Beyond that we leave the plot unsnapped and report
it — the gate then withholds its €, which is the correct outcome. We never move a plot to a
cell whose climate isn't its own.

Idempotent: re-running snaps only what is not already on a scored cell.

    python -m scripts.snap_plots_to_scored_grid                    # all commodities
    python -m scripts.snap_plots_to_scored_grid --commodity Cocoa
    python -m scripts.snap_plots_to_scored_grid --dry-run
"""
from __future__ import annotations

import argparse
import math
import sys

import h3
from sqlalchemy import text

from core.db.session import get_session


def _latlng(cell: str):
    try:
        return h3.cell_to_latlng(cell)          # h3 v4
    except AttributeError:
        return h3.h3_to_geo(cell)               # h3 v3


def _km(a_lat, a_lon, b_lat, b_lon) -> float:
    r = 6371.0
    p = math.radians
    dlat, dlon = p(b_lat - a_lat), p(b_lon - a_lon)
    x = math.sin(dlat / 2) ** 2 + math.cos(p(a_lat)) * math.cos(p(b_lat)) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commodity", help="only this commodity (default: all calibrated ones)")
    ap.add_argument("--max-km", type=float, default=25.0,
                    help="never snap further than this (default 25km ~ one ERA5-Land pixel)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    snapped = already = unreachable = no_driver = 0
    with get_session() as s:
        # Every plot + the hazard its crop+origin is calibrated against.
        rows = s.execute(text("""
            SELECT p.plot_id::text AS plot_id, p.plot_name, p.h3_cell, p.country,
                   CAST(p.latitude AS FLOAT) AS lat, CAST(p.longitude AS FLOAT) AS lon,
                   co.name AS commodity, cal.hazard_driver
            FROM   sc_sourcing_plots p
            JOIN   sc_commodities co ON co.commodity_id = p.commodity_id
            LEFT   JOIN sc_commodity_calibration cal
                   ON cal.commodity_id = p.commodity_id AND cal.origin = p.country
            WHERE  (CAST(:c AS TEXT) IS NULL OR co.name = CAST(:c AS TEXT))
            ORDER  BY co.name, p.country
        """), {"c": args.commodity}).mappings().all()

        # Cells actually scored, per hazard (live rows, standing lane only — a nowcast must
        # never be what a standing crop number snaps onto).
        by_hazard: dict[str, list] = {}
        for hz in {r["hazard_driver"] for r in rows if r["hazard_driver"]}:
            cells = s.execute(text("""
                SELECT DISTINCT h3_cell FROM canonical_scores
                WHERE hazard_type = :h AND valid_to IS NULL AND score_lane = 'standing'
            """), {"h": hz}).scalars().all()
            by_hazard[hz] = [(c, *_latlng(c)) for c in cells]
            print(f"{hz}: {len(cells)} scored cells")

        for r in rows:
            hz = r["hazard_driver"]
            if not hz:
                no_driver += 1
                print(f"  – {r['commodity']:12s} {r['country']}  {r['plot_name'][:34]:34s} "
                      f"no calibrated driver → cannot be snapped (crop needs a backtest first)")
                continue

            scored = by_hazard.get(hz) or []
            scored_set = {c for c, _, _ in scored}
            if r["h3_cell"] in scored_set:
                already += 1
                continue

            if not scored:
                unreachable += 1
                continue
            cell, dist = min(((c, _km(r["lat"], r["lon"], la, lo)) for c, la, lo in scored),
                             key=lambda t: t[1])
            if dist > args.max_km:
                unreachable += 1
                print(f"  ! {r['commodity']:12s} {r['country']}  {r['plot_name'][:34]:34s} "
                      f"nearest {hz} cell is {dist:.1f} km away (> {args.max_km} km) → left unsnapped, € stays withheld")
                continue

            print(f"  ✓ {r['commodity']:12s} {r['country']}  {r['plot_name'][:34]:34s} "
                  f"→ {cell} ({dist:.1f} km, {hz})")
            if not args.dry_run:
                s.execute(text("UPDATE sc_sourcing_plots SET h3_cell = :c WHERE plot_id = :p"),
                          {"c": cell, "p": r["plot_id"]})
            snapped += 1

    print(f"\nsnapped {snapped} · already on grid {already} · "
          f"unreachable {unreachable} · no calibrated driver {no_driver}"
          + ("  [DRY RUN — nothing written]" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
