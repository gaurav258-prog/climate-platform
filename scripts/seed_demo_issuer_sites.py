"""The demo issuers' sites where their names say (E316; the product owner's decision of 2026-10-22). The demo book's
sites once sat on the only cells scored then, near Valencia, while named and stated as Cologne, Stockholm, Malmö or
Rotterdam — so a German utility's head office was scored, and its loss read, in Spain. This moves each existing site in
place (the seed itself wipes and re-creates the issuers, which would take every manager's positions and figures with
them): its coordinates, cell and region from scripts/seed_demo_asset_manager.SITES, the 'Unscored Depot' without a
location (its location is not known), and then scores the new cells on demand, as an address lookup does — so a site's
scores are whatever the maps say there. Idempotent.

    venv/bin/python -m scripts.seed_demo_issuer_sites              # move and score
    venv/bin/python -m scripts.seed_demo_issuer_sites --no-score   # move only
"""
from __future__ import annotations

import sys

from sqlalchemy import text

from core.db.session import get_session
from scripts.seed_demo_asset_manager import ISSUERS, LEIS, SITES, place


def move() -> list[dict]:
    """Each demo site set to its place; returns what changed."""
    changed = []
    with get_session() as s:
        for name, _t, country, *_rest, facilities, _e in ISSUERS:
            for fname, *_ in facilities:
                at = {**place(fname), "c": country}
                row = s.execute(text("""
                    UPDATE issuer_facilities f SET latitude = :lat, longitude = :lon, h3_cell = :cell, region = :region,
                                                   country = :c
                    FROM issuers i
                    WHERE i.issuer_id = f.issuer_id AND i.lei = :lei AND f.name = :n
                      AND (f.latitude, f.longitude, f.h3_cell, f.region, f.country)
                          IS DISTINCT FROM (CAST(:lat AS float8), CAST(:lon AS float8), :cell, :region, :c)
                    RETURNING f.facility_id::text"""), {"lei": LEIS[name], "n": fname, **at}).first()
                if row:
                    changed.append({"site": fname, "issuer": name, **at})
        s.commit()
    return changed


def score() -> dict:
    """Score the demo sites' cells on demand (services.scoring.on_demand.process_new_cells) — the cells not yet scored."""
    from services.scoring.on_demand import process_new_cells
    cells = {p["cell"]: (p["lat"], p["lon"]) for p in (place(n) for n in SITES) if p["cell"]}
    return process_new_cells(cells)


def main() -> None:
    changed = move()
    print(f"{len(changed)} demo sites moved to their places")
    for c in changed:
        print(f"  {c['issuer']} · {c['site']}: {c['lat']}, {c['lon']} ({c['region']}, {c['c']})")
    if "--no-score" not in sys.argv:
        print(score())


if __name__ == "__main__":
    main()
