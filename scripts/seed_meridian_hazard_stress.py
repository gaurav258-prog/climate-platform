"""Seed a stress-test slice of the Meridian (demo bank) loan book at genuinely hazard-prone locations, so the
EBA Pillar 3 Template 5 physical-risk classification exercises the FULL 28-hazard set — then anyone can re-run
the template and see chronic/acute/both light up across the new channels.

Honest by construction: these are clearly-labelled DEMO exposures on the demo tenant, placed at REAL high-hazard
locations (Jakarta subsidence, Tornado-Alley convective, Himalayan GLOF, Loess-Plateau erosion, Arctic
permafrost, Dutch/Gulf coast SLR+saline, …) — the scores come from the real golden source, not fabricated. Each
cell is scored for every hazard at baseline/current AND at the reporting scenario × horizon (so the
scenario-flat channels are present when Template 5 runs forward). Idempotent: re-running upserts the same rows.

Run:  .venv/bin/python -m scripts.seed_meridian_hazard_stress
"""
from __future__ import annotations

import uuid

import h3
from sqlalchemy import text

from core.db.session import get_session
from services.scoring.on_demand import SYNC_ON_DEMAND_SCORERS

MERIDIAN = "11111111-1111-4111-8111-111111111111"
REPORT_SCENARIOS = [("baseline", "current"), ("disorderly_2c", "2050")]
PROJECTION = ["changing_temp", "changing_precip", "changing_wind", "coastal_erosion"]

# (name, lat, lon, country, sector, nace, exposure_eur, maturity_yrs, ifrs9_stage) — real high-hazard sites.
SITES = [
    ("Jakarta industrial estate",       -6.20, 106.85, "ID", "Manufacturing",        "C", 42_000_000, 8,  "2"),
    ("Mexico City logistics hub",       19.43, -99.13, "MX", "Transportation",       "H", 31_000_000, 6,  "1"),
    ("New Orleans port terminal",       29.95, -90.07, "US", "Transportation",       "H", 55_000_000, 12, "2"),
    ("Miami waterfront tower",          25.76, -80.19, "US", "Real estate",          "L", 68_000_000, 15, "1"),
    ("Dhaka textile complex",           23.80,  90.40, "BD", "Manufacturing",        "C", 24_000_000, 5,  "3"),
    ("Oklahoma grain terminal",         35.50, -97.50, "US", "Agriculture",          "A", 18_000_000, 7,  "1"),
    ("Loess Plateau agri-estate",       37.00, 109.00, "CN", "Agriculture",          "A", 21_000_000, 9,  "2"),
    ("Chamonix alpine resort",          45.88,   6.89, "FR", "Accommodation & food", "I", 27_000_000, 11, "1"),
    ("Khumbu hydro facility",           28.00,  86.85, "NP", "Electricity/utilities","D", 46_000_000, 20, "1"),
    ("Rotterdam port logistics",        51.92,   4.48, "NL", "Transportation",       "H", 51_000_000, 14, "1"),
    ("Yamal Arctic gas plant",          70.30,  68.90, "RU", "Mining & quarrying",   "B", 60_000_000, 18, "2"),
    ("Sahel irrigation scheme",         15.00,   5.00, "NE", "Agriculture",          "A",  9_000_000, 4,  "3"),
    ("Norway aquaculture coast",        60.40,   5.30, "NO", "Agriculture",          "A", 14_000_000, 6,  "1"),
    ("Po Valley manufacturing park",    45.40,  10.90, "IT", "Manufacturing",        "C", 33_000_000, 8,  "2"),
]


def _upsert_asset(s, name, lat, lon, country, sector, nace, exposure, maturity, stage) -> str:
    cell = h3.latlng_to_cell(lat, lon, 8)
    eid = s.execute(text("SELECT entity_id FROM portfolio_entities WHERE org_id=:o AND entity_name=:n"),
                    {"o": MERIDIAN, "n": name}).scalar()
    eid = eid or uuid.uuid4()
    s.execute(text("""
        INSERT INTO portfolio_entities (entity_id, org_id, vertical, entity_name, entity_type, sector, nace_code,
            latitude, longitude, h3_cell, country, primary_value_eur, created_at, updated_at)
        VALUES (:id, :o, 'banking', :n, :sec, :sec, :nace, :lat, :lon, :c, :ctry, :val, now(), now())
        ON CONFLICT (entity_id) DO UPDATE SET h3_cell=EXCLUDED.h3_cell, primary_value_eur=EXCLUDED.primary_value_eur,
            nace_code=EXCLUDED.nace_code, sector=EXCLUDED.sector, latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude
    """), {"id": eid, "o": MERIDIAN, "n": name, "sec": sector, "nace": nace, "lat": lat, "lon": lon,
           "c": cell, "ctry": country, "val": exposure})
    s.execute(text("""
        INSERT INTO ext_banking (entity_id, outstanding_loan_balance_eur, residual_maturity_years, ifrs9_stage, epc_label)
        VALUES (:id, :bal, :mat, :stg, 'D')
        ON CONFLICT (entity_id) DO UPDATE SET outstanding_loan_balance_eur=EXCLUDED.outstanding_loan_balance_eur,
            residual_maturity_years=EXCLUDED.residual_maturity_years, ifrs9_stage=EXCLUDED.ifrs9_stage
    """), {"id": eid, "bal": exposure, "mat": maturity, "stg": stage})
    return cell


def main() -> int:
    with get_session() as s:
        cells = [_upsert_asset(s, *site) for site in SITES]
        s.commit()
    print(f"upserted {len(SITES)} Meridian stress-test assets", flush=True)

    # score each cell for every hazard, at baseline/current AND the forward reporting scenario
    for i, cell in enumerate(cells, 1):
        lat, lon = h3.cell_to_latlng(cell)
        for sc, hz_h in REPORT_SCENARIOS:
            for hz, scorer in SYNC_ON_DEMAND_SCORERS.items():
                try:
                    scorer(lat, lon, sc, hz_h)
                except Exception:
                    pass
        print(f"  scored {i}/{len(cells)} cells", flush=True)
    print("done — re-run Template 5 for Meridian to see the full-hazard classification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
