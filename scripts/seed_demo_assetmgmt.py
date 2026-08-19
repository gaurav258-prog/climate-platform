"""
Seed a realistic demo holdings book into portfolio_entities (the unified
schema -- see the b9c0d1e2f3a4 migration; this used to write directly to
assetmgmt_holdings, now retired) for Nordkap Asset Management -- the
Portfolio climate VaR & screening workspace needs holdings to project
canonical_scores onto, the same role every other seed_demo_*.py script
plays. Deliberately a DIVERSIFIED book across many NACE codes/sectors
(unlike real estate's single-sector book) so the EU Taxonomy rollup shows a
genuine mix of eligible/not_eligible rather than one uniform status --
demonstrating the classifier's real discrimination, not just echoing one
NACE code. Placed on real scored ground (Valencia flood zone, EU wildfire
cells) plus European financial-centre holdings that fall outside scored
cells (honest 'no_canonical_score'). Idempotent: clears the demo org first.

Run:  .venv/bin/python scripts/seed_demo_assetmgmt.py
"""
import random
import uuid

import h3
from global_land_mask import globe
from sqlalchemy import text

from core.db.session import get_session

random.seed(31)
NORDKAP = "44444444-4444-4444-8444-444444444444"

# sector -> (nace_code, value range €m) -- deliberately spans multiple Taxonomy
# outcomes: 68.20 (real estate) and 35.11 (electricity generation) are eligible
# per ml/regulatory/eu_taxonomy_classifier.py; the rest are not_eligible.
SECTORS = [
    ("Real estate", "68.20", (5, 60)),
    ("Electricity generation", "35.11", (10, 90)),
    ("Manufacturing", "25.50", (3, 40)),
    ("Logistics & warehousing", "52.10", (4, 35)),
    ("Hospitality", "55.10", (2, 25)),
    ("Agriculture & food", "01.50", (1, 20)),
    ("Software & IT services", "62.01", (2, 45)),
    ("Retail", "47.19", (2, 30)),
]

CITIES = [
    ("Stockholm", 59.329, 18.069), ("Oslo", 59.914, 10.752),
    ("Copenhagen", 55.676, 12.568), ("Helsinki", 60.169, 24.938),
    ("Frankfurt", 50.110, 8.682), ("Zurich", 47.377, 8.542),
    ("Amsterdam", 52.370, 4.895), ("Vienna", 48.208, 16.373),
]


def on_land(cell):
    lat, lon = h3.cell_to_latlng(cell)
    return bool(globe.is_land(lat, lon))


def scored_cells(session, hazard, limit):
    rows = session.execute(text("""
        SELECT h3_cell FROM canonical_scores
        WHERE hazard_type = :h AND valid_to IS NULL
        ORDER BY risk_score DESC LIMIT :n
    """), {"h": hazard, "n": limit}).scalars().all()
    return [c for c in rows if on_land(c)]


def make_holding(lat, lon, h3_cell, region, name_hint=None):
    sector, nace, (vmin, vmax) = random.choice(SECTORS)
    value = round(random.uniform(vmin, vmax), 1) * 1_000_000
    country = "ES" if -9.6 <= lon <= 3.4 and 36.0 <= lat <= 43.9 else "EU"
    return {
        "holding_id": str(uuid.uuid4()), "org_id": NORDKAP,
        "holding_name": name_hint or f"{region} {sector.split(' ')[0]} {random.randint(1, 999)}",
        "sector": sector, "nace_code": nace,
        "latitude": round(lat, 5), "longitude": round(lon, 5), "h3_cell": h3_cell,
        "country": country, "region": region, "position_value_eur": value,
    }


def main():
    with get_session() as s:
        flood = scored_cells(s, "flood", 336)
        wildfire = random.sample(scored_cells(s, "wildfire", 8000), 2000)

        holdings = []
        for c in random.sample(flood, min(20, len(flood))):
            lat, lon = h3.cell_to_latlng(c)
            holdings.append(make_holding(lat, lon, c, "Valencia (flood zone)"))
        for c in random.sample(wildfire, min(15, len(wildfire))):
            lat, lon = h3.cell_to_latlng(c)
            holdings.append(make_holding(lat, lon, c, "Iberia (wildfire zone)"))
        for _ in range(35):
            name, lat, lon = random.choice(CITIES)
            for _try in range(20):
                jlat, jlon = lat + random.uniform(-0.06, 0.06), lon + random.uniform(-0.06, 0.06)
                if globe.is_land(jlat, jlon):
                    break
            else:
                jlat, jlon = lat, lon
            holdings.append(make_holding(jlat, jlon, h3.latlng_to_cell(jlat, jlon, 8), name))

        s.execute(text("DELETE FROM portfolio_entities WHERE org_id = :o AND vertical = 'assetmgmt'"), {"o": NORDKAP})
        s.execute(text("""
            INSERT INTO portfolio_entities
                (entity_id, org_id, vertical, entity_name, sector, nace_code, latitude, longitude,
                 h3_cell, country, region, entity_type, primary_value_eur)
            VALUES
                (:holding_id, :org_id, 'assetmgmt', :holding_name, :sector, :nace_code, :latitude, :longitude,
                 :h3_cell, :country, :region, :sector, :position_value_eur)
        """), holdings)

        total = sum(h["position_value_eur"] for h in holdings)
        print(f"seeded {len(holdings)} holdings, total portfolio €{total/1e6:.1f}m, org {NORDKAP}")
        scored = s.execute(text("""
            SELECT count(DISTINCT e.entity_id) FROM portfolio_entities e
            JOIN canonical_scores cs ON cs.h3_cell = e.h3_cell AND cs.valid_to IS NULL
            WHERE e.org_id = :o AND e.vertical = 'assetmgmt'
        """), {"o": NORDKAP}).scalar()
        print(f"{scored} of {len(holdings)} holdings fall in scored cells (rest = no_canonical_score)")


if __name__ == "__main__":
    main()
