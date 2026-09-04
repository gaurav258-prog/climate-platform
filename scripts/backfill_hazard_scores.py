"""Backfill on-demand hazard scores for every customer asset — so existing books show the FULL hazard set.

The on-demand hazard channels (subsidence, soil erosion, severe convective, permafrost, coastal erosion,
saline intrusion, glacial-lake outburst, ocean acidification, avalanche, solifluction, soil degradation,
changing wind, …) score a cell only when it is first processed. Assets loaded BEFORE a channel existed keep
their old scores until the cell is re-scored. This walks every located customer asset and scores its cell for
the full sync set (at baseline/current) plus the forward-projection channels (at each scenario × horizon), so
each asset's drill-down reflects the current coverage.

Truthful by construction: it scores each asset at the CENTRE of its stored H3 cell (h3.cell_to_latlng) — not
the possibly-rounded stored lat/lon, which can land on a neighbouring cell — and every scorer only writes a
row where the hazard genuinely applies (off-domain / no-data returns not_applicable / insufficient_data and
inserts nothing). Idempotent: an already-scored (cell, hazard, scenario, horizon) is a cached-hit no-op, and
one hazard failing never aborts the asset.

Run:  .venv/bin/python -m scripts.backfill_hazard_scores
"""
from __future__ import annotations

import h3
from sqlalchemy import text

from core.db.session import get_session
from services.scoring.on_demand import SYNC_ON_DEMAND_SCORERS

# Customer-asset tables that carry an h3_cell (NOT the golden-source baseline/feature grids).
ASSET_TABLES = [
    "sc_sourcing_plots", "sc_company_sites", "bank_assets", "insurance_policies",
    "realestate_properties", "assetmgmt_holdings", "issuer_facilities", "portfolio_entities",
]
# Forward-looking channels are defined only under a projection scenario × horizon.
PROJECTION_HAZARDS = ["changing_temp", "changing_precip", "changing_wind", "coastal_erosion"]
SCENARIOS = ["orderly_1_5c", "disorderly_2c", "hot_house_3_5c"]
HORIZONS = ["2030", "2050", "2100"]


def _asset_cells() -> list[str]:
    cells: set[str] = set()
    with get_session() as s:
        for t in ASSET_TABLES:
            try:
                cells.update(s.execute(text(f"SELECT DISTINCT h3_cell FROM {t} WHERE h3_cell IS NOT NULL")).scalars().all())
            except Exception as e:  # a sector table may be absent in a given deployment
                print(f"  (skip {t}: {str(e)[:60]})")
    return sorted(cells)


def main() -> int:
    cells = _asset_cells()
    print(f"backfilling {len(cells)} distinct customer-asset cells", flush=True)
    scored: dict[str, int] = {}

    def _tally(hz: str, res: dict) -> None:
        if res.get("status") in ("scored", "cached_hit"):
            scored[hz] = scored.get(hz, 0) + 1

    for i, cell in enumerate(cells, 1):
        lat, lon = h3.cell_to_latlng(cell)   # exact centre → scores land on THIS cell
        # 1) full sync set at baseline/current (the scenario-flat channels; projection ones no-op here)
        for hz, scorer in SYNC_ON_DEMAND_SCORERS.items():
            try:
                _tally(hz, scorer(lat, lon))
            except Exception:
                pass
        # 2) forward-projection channels across scenario × horizon
        for hz in PROJECTION_HAZARDS:
            scorer = SYNC_ON_DEMAND_SCORERS.get(hz)
            if not scorer:
                continue
            for sc in SCENARIOS:
                for hz_h in HORIZONS:
                    try:
                        _tally(hz, scorer(lat, lon, sc, hz_h))
                    except Exception:
                        pass
        if i % 50 == 0 or i == len(cells):
            print(f"  {i}/{len(cells)} cells done", flush=True)

    print("\nper-hazard cells scored (scored + cached):")
    for hz in sorted(scored, key=lambda k: -scored[k]):
        print(f"  {hz:24s} {scored[hz]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
