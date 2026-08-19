"""
Seed a realistic demo property book into portfolio_entities/ext_insurance
(the unified schema -- see the b9c0d1e2f3a4 migration; this used to write
directly to insurance_policies, now retired) for Iberia Mutual — the
underwriting flagship needs policies to project canonical_scores onto, the
same role seed_demo_loanbook.py plays for the bank and seed_demo_supply.py
plays for agriculture. Placed on real scored ground (Valencia flood zone,
EU/Iberia wildfire cells) plus a few Iberian cities that fall outside scored
cells (honest 'no_canonical_score'), same true-story mix as the loan book.
Idempotent: clears the demo org's policies first (cascades to any
configured parametric triggers on those policies).

Run:  .venv/bin/python scripts/seed_demo_insurance.py
"""
import random
import uuid

import h3
from global_land_mask import globe
from sqlalchemy import text

from core.db.session import get_session

random.seed(7)
IBERIA = "22222222-2222-4222-8222-222222222222"

# policy_type -> (sum insured range €m, deductible pct)
POLICY_TYPES = [
    ("property", (0.3, 2.0), 0.02),      # residential
    ("property", (1.0, 15.0), 0.03),     # commercial
]

CITIES = [
    ("Madrid", 40.417, -3.703), ("Barcelona", 41.385, 2.173),
    ("Lisbon", 38.722, -9.139), ("Seville", 37.389, -5.984),
    ("Porto", 41.158, -8.629), ("Bilbao", 43.263, -2.935),
    ("Malaga", 36.721, -4.421), ("Zaragoza", 41.649, -0.889),
]


def on_land(cell):
    lat, lon = h3.cell_to_latlng(cell)
    return bool(globe.is_land(lat, lon))


def scored_cells_in_iberia(session, hazard, limit):
    rows = session.execute(text("""
        SELECT h3_cell FROM canonical_scores
        WHERE hazard_type = :h AND valid_to IS NULL
        ORDER BY risk_score DESC LIMIT :n
    """), {"h": hazard, "n": limit}).scalars().all()
    out = []
    for c in rows:
        lat, lon = h3.cell_to_latlng(c)
        if 35.5 <= lat <= 44.0 and -9.6 <= lon <= 4.5 and globe.is_land(lat, lon):
            out.append(c)
    return out


CONSTRUCTION_TYPES = ["frame", "joisted_masonry", "non_combustible", "masonry_non_combustible", "fire_resistive"]


def make_policy(lat, lon, h3_cell, region, name_hint=None):
    ptype, (vmin, vmax), ded = random.choice(POLICY_TYPES)
    tiv = round(random.uniform(vmin, vmax), 2) * 1_000_000
    country = "PT" if lon < -6.5 else "ES"
    # Real Statement-of-Values shape: TIV split into building/contents/business
    # interruption (see ml/scoring/insurance_pricing.py / services/templates/workbook.py's
    # SOV template), not one lump figure -- roughly 75/15/10% split, a real-world rule of thumb.
    building = round(tiv * 0.75, 2)
    contents = round(tiv * 0.15, 2)
    bi = round(tiv - building - contents, 2)
    return {
        "policy_id": str(uuid.uuid4()), "org_id": IBERIA,
        "policy_name": name_hint or f"{region} {ptype} {random.randint(1, 999)}",
        "policy_type": ptype, "latitude": round(lat, 5), "longitude": round(lon, 5),
        "h3_cell": h3_cell, "country": country, "region": region,
        "sum_insured_eur": tiv, "deductible_pct": ded,
        "building_value_eur": building, "contents_value_eur": contents, "business_interruption_value_eur": bi,
        "construction_type": random.choice(CONSTRUCTION_TYPES),
        "year_built": random.randint(1965, 2020), "number_of_stories": random.randint(1, 8),
    }


def main():
    with get_session() as s:
        flood = scored_cells_in_iberia(s, "flood", 7000)
        wildfire = scored_cells_in_iberia(s, "wildfire", 20000)

        policies = []
        for c in random.sample(flood, min(70, len(flood))):
            lat, lon = h3.cell_to_latlng(c)
            policies.append(make_policy(lat, lon, c, "Valencia (flood zone)"))
        for c in random.sample(wildfire, min(40, len(wildfire))):
            lat, lon = h3.cell_to_latlng(c)
            policies.append(make_policy(lat, lon, c, "Iberia (wildfire zone)"))
        for _ in range(35):
            name, lat, lon = random.choice(CITIES)
            for _try in range(20):
                jlat, jlon = lat + random.uniform(-0.06, 0.06), lon + random.uniform(-0.06, 0.06)
                if globe.is_land(jlat, jlon):
                    break
            else:
                jlat, jlon = lat, lon
            policies.append(make_policy(jlat, jlon, h3.latlng_to_cell(jlat, jlon, 8), name))

        s.execute(text("DELETE FROM portfolio_entities WHERE org_id = :o AND vertical = 'insurance'"), {"o": IBERIA})
        s.execute(text("""
            INSERT INTO portfolio_entities
                (entity_id, org_id, vertical, entity_name, entity_type, latitude, longitude,
                 h3_cell, country, region, primary_value_eur,
                 construction_type, year_built, number_of_stories)
            VALUES
                (:policy_id, :org_id, 'insurance', :policy_name, :policy_type, :latitude, :longitude,
                 :h3_cell, :country, :region, :sum_insured_eur,
                 :construction_type, :year_built, :number_of_stories)
        """), policies)
        s.execute(text("""
            INSERT INTO ext_insurance
                (entity_id, deductible_pct, building_value_eur, contents_value_eur, business_interruption_value_eur)
            VALUES
                (:policy_id, :deductible_pct, :building_value_eur, :contents_value_eur, :business_interruption_value_eur)
        """), policies)

        total = sum(p["sum_insured_eur"] for p in policies)
        print(f"seeded {len(policies)} policies, total sum insured €{total/1e6:.1f}m, org {IBERIA}")
        scored = s.execute(text("""
            SELECT count(DISTINCT e.entity_id) FROM portfolio_entities e
            JOIN canonical_scores cs ON cs.h3_cell = e.h3_cell AND cs.valid_to IS NULL
            WHERE e.org_id = :o AND e.vertical = 'insurance'
        """), {"o": IBERIA}).scalar()
        print(f"{scored} of {len(policies)} policies fall in scored cells (rest = no_canonical_score)")


if __name__ == "__main__":
    main()
