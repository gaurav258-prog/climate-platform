"""
Seed a realistic demo property book into portfolio_entities/ext_realestate
(the unified schema -- see the b9c0d1e2f3a4 migration; this used to write
directly to realestate_properties, now retired) for Stellar Logistics REIT --
the Portfolio & NOI impact workspace needs properties to
project canonical_scores onto, the same role seed_demo_loanbook.py plays for
the bank, seed_demo_insurance.py for the insurer, and seed_demo_supply.py for
agriculture. A pan-European logistics/light-industrial portfolio (matching
the fund's own name), placed on real scored ground (Valencia flood zone, EU
wildfire cells) plus logistics-hub cities that fall outside scored cells
(honest 'no_canonical_score'). Idempotent: clears the demo org's properties
first.

Run:  .venv/bin/python scripts/seed_demo_realestate.py
"""
import random
import uuid

import h3
from global_land_mask import globe
from sqlalchemy import text

from core.db.session import get_session

random.seed(19)
STELLAR = "33333333-3333-4333-8333-333333333333"

# property_type -> (value range €m, NOI yield range -- a real commercial cap-rate
# band, not an arbitrary number: NOI = value * yield)
PROPERTY_TYPES = [
    ("logistics", (8, 55), (0.050, 0.068)),
    ("light_industrial", (5, 30), (0.055, 0.070)),
    ("office", (10, 70), (0.045, 0.058)),
    ("retail", (4, 25), (0.048, 0.062)),
]

CITIES = [
    ("Rotterdam", 51.924, 4.478), ("Antwerp", 51.221, 4.400),
    ("Duisburg", 51.435, 6.762), ("Lyon", 45.764, 4.835),
    ("Hamburg", 53.551, 9.994), ("Katowice", 50.264, 19.024),
    ("Bologna", 44.494, 11.342), ("Zaragoza", 41.649, -0.889),
]

CONSTRUCTION_TYPES = ["frame", "joisted_masonry", "non_combustible", "masonry_non_combustible", "fire_resistive"]


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


def make_property(lat, lon, h3_cell, region, name_hint=None):
    ptype, (vmin, vmax), (ymin, ymax) = random.choice(PROPERTY_TYPES)
    value = round(random.uniform(vmin, vmax), 1) * 1_000_000
    noi = round(value * random.uniform(ymin, ymax), 2)
    country = "ES" if -9.6 <= lon <= 3.4 and 36.0 <= lat <= 43.9 else "EU"
    return {
        "property_id": str(uuid.uuid4()), "org_id": STELLAR,
        "property_name": name_hint or f"{region} {ptype.replace('_', ' ').title()} {random.randint(1, 99)}",
        "property_type": ptype, "latitude": round(lat, 5), "longitude": round(lon, 5),
        "h3_cell": h3_cell, "country": country, "region": region,
        "property_value_eur": value, "annual_noi_eur": noi,
        "construction_type": random.choice(CONSTRUCTION_TYPES),
        "year_built": random.randint(1978, 2022), "number_of_stories": random.randint(1, 6),
    }


def main():
    with get_session() as s:
        flood = scored_cells(s, "flood", 336)
        wildfire = random.sample(scored_cells(s, "wildfire", 8000), 2000)

        properties = []
        for c in random.sample(flood, min(25, len(flood))):
            lat, lon = h3.cell_to_latlng(c)
            properties.append(make_property(lat, lon, c, "Valencia (flood zone)"))
        for c in random.sample(wildfire, min(15, len(wildfire))):
            lat, lon = h3.cell_to_latlng(c)
            properties.append(make_property(lat, lon, c, "Iberia (wildfire zone)"))
        for _ in range(30):
            name, lat, lon = random.choice(CITIES)
            for _try in range(20):
                jlat, jlon = lat + random.uniform(-0.06, 0.06), lon + random.uniform(-0.06, 0.06)
                if globe.is_land(jlat, jlon):
                    break
            else:
                jlat, jlon = lat, lon
            properties.append(make_property(jlat, jlon, h3.latlng_to_cell(jlat, jlon, 8), name))

        s.execute(text("DELETE FROM portfolio_entities WHERE org_id = :o AND vertical = 'realestate'"), {"o": STELLAR})
        s.execute(text("""
            INSERT INTO portfolio_entities
                (entity_id, org_id, vertical, entity_name, entity_type, latitude, longitude,
                 h3_cell, country, region, primary_value_eur, construction_type, year_built, number_of_stories)
            VALUES
                (:property_id, :org_id, 'realestate', :property_name, :property_type, :latitude, :longitude,
                 :h3_cell, :country, :region, :property_value_eur,
                 :construction_type, :year_built, :number_of_stories)
        """), properties)
        s.execute(text("""
            INSERT INTO ext_realestate (entity_id, annual_noi_eur)
            VALUES (:property_id, :annual_noi_eur)
        """), properties)

        total = sum(p["property_value_eur"] for p in properties)
        total_noi = sum(p["annual_noi_eur"] for p in properties)
        print(f"seeded {len(properties)} properties, total value €{total/1e6:.1f}m, "
              f"total NOI €{total_noi/1e6:.1f}m, org {STELLAR}")
        scored = s.execute(text("""
            SELECT count(DISTINCT e.entity_id) FROM portfolio_entities e
            JOIN canonical_scores cs ON cs.h3_cell = e.h3_cell AND cs.valid_to IS NULL
            WHERE e.org_id = :o AND e.vertical = 'realestate'
        """), {"o": STELLAR}).scalar()
        print(f"{scored} of {len(properties)} properties fall in scored cells (rest = no_canonical_score)")


if __name__ == "__main__":
    main()
