"""
Seed a realistic demo bank loan book into portfolio_entities/ext_banking (the
unified schema -- see the b9c0d1e2f3a4 migration; this used to write directly
to bank_assets, now retired).

The banking flagship needs assets to project canonical_scores onto. This inserts
~120 assets for one demo org, deliberately placing a chunk of them in cells that
ARE already scored (Valencia flood zone → real High/Very-High physical risk; EU
wildfire cells → Low/Medium) so the portfolio tells a true story, plus assets in
European financial centres that fall outside scored cells (honest
`no_canonical_score`). Idempotent: clears the demo org first.

Run:  .venv/bin/python scripts/seed_demo_loanbook.py
"""
import json
import random
import uuid
from datetime import date, timedelta

import h3
from global_land_mask import globe
from sqlalchemy import text

from core.db.session import get_session
from ml.regulatory.eu_taxonomy_classifier import classify_taxonomy


def on_land(cell):
    """A bank's financed assets must be on land — flood cells can fall over water."""
    lat, lon = h3.cell_to_latlng(cell)
    return bool(globe.is_land(lat, lon))

random.seed(42)
DEMO_ORG = "11111111-1111-4111-8111-111111111111"

# sector → (asset_type, nace, gics, value range €m, lifespan, ghg/€m profile)
SECTORS = [
    ("Commercial real estate", "commercial_real_estate", "68.20", "60101010", (8, 60), 50, 18),
    ("Residential mortgages", "residential_real_estate", "68.20", "60101070", (0.3, 2.5), 60, 12),
    ("Manufacturing", "industrial", "25.50", "20104010", (10, 80), 35, 140),
    ("Energy & utilities", "energy", "35.11", "55101010", (20, 120), 40, 320),
    ("Logistics & transport", "logistics", "52.10", "20303010", (6, 45), 40, 90),
    ("Hospitality", "hospitality", "55.10", "25301020", (4, 35), 45, 60),
    ("Agriculture & food", "agriculture", "01.50", "30202010", (1, 20), 30, 110),
]

COUNTRY_BOXES = [  # (ISO-2, lon_min, lon_max, lat_min, lat_max) — first match wins
    ("PT", -9.6, -6.0, 37.0, 42.2), ("ES", -9.4, 3.4, 36.0, 43.9),
    ("FR", -5.2, 8.3, 42.3, 51.1), ("IT", 6.5, 18.6, 36.5, 47.1),
    ("DE", 5.8, 15.1, 47.2, 55.1), ("GR", 19.3, 28.3, 34.8, 41.8),
    ("GB", -8.2, 1.8, 49.9, 59.0), ("PL", 14.1, 24.2, 49.0, 54.9),
    ("GT", -91.0, -90.6, 14.3, 14.7),
    ("PR", -67.3, -65.2, 17.8, 18.6),
]

# Guatemala volcanic-hazard demo assets — real sites near Fuego, both scored via
# scripts/score_volcanic_event.py (hazard_type='volcanic'). Not random placements:
# one echoes the real San Miguel Los Lotes destruction footprint (proximal-driven),
# one is Antigua Guatemala itself (a UNESCO-heritage hospitality economy, ashfall-
# exposed but outside the PDC's path) — the same sites backtest_volcanic.py checks.
GUATEMALA_ASSETS = [
    ("Los Lotes commercial 1", "Commercial real estate", 14.4180, -90.8590, "San Miguel Los Lotes"),
    ("Antigua hospitality 1", "Hospitality", 14.5586, -90.7295, "Antigua Guatemala"),
]

# Puerto Rico storm-hazard demo assets — real sites tested against Hurricane Maria's
# actual 2017 track via scripts/score_storm_event.py (hazard_type='storm'). San Juan
# sat closest to the eyewall (severe direct hit, real ~80% grid destruction); Ponce,
# on the south coast, was still hit hard but farther from the track — the same
# proximal-vs-farther contrast used for Guatemala's volcanic assets.
PUERTO_RICO_ASSETS = [
    ("San Juan commercial 1", "Commercial real estate", 18.4655, -66.1057, "San Juan"),
    ("Ponce hospitality 1", "Hospitality", 18.0111, -66.6141, "Ponce"),
]


def country_for(lat, lon):
    for code, lo, hi, la, ha in COUNTRY_BOXES:
        if lo <= lon <= hi and la <= lat <= ha:
            return code
    return "EU"


def scored_cells(session, hazard, limit):
    rows = session.execute(text("""
        SELECT h3_cell FROM canonical_scores
        WHERE hazard_type = :h AND valid_to IS NULL
        ORDER BY risk_score DESC LIMIT :n
    """), {"h": hazard, "n": limit}).scalars().all()
    return list(rows)


# European financial centres (assets here usually fall outside scored cells)
CITIES = [
    ("Frankfurt", 50.110, 8.682), ("Paris", 48.857, 2.352), ("Madrid", 40.417, -3.703),
    ("Milan", 45.464, 9.190), ("Amsterdam", 52.370, 4.895), ("Munich", 48.137, 11.576),
    ("Lisbon", 38.722, -9.139), ("Lyon", 45.764, 4.835), ("Hamburg", 53.551, 9.994),
    ("Barcelona", 41.385, 2.173), ("Rome", 41.903, 12.496), ("Porto", 41.158, -8.629),
]


def make_asset(lat, lon, h3_cell, region, force_sector=None, name_override=None):
    if force_sector:
        sector, atype, nace, gics, (vmin, vmax), lifespan, ghg_per_m = next(
            s for s in SECTORS if s[0] == force_sector)
    else:
        sector, atype, nace, gics, (vmin, vmax), lifespan, ghg_per_m = random.choice(SECTORS)
    value_m = round(random.uniform(vmin, vmax), 1)
    value = value_m * 1_000_000
    country = country_for(lat, lon)
    scope1 = round(value_m * ghg_per_m * random.uniform(0.4, 0.7), 1)
    # A real "loan tape" needs the loan side, not just the collateral value —
    # LTV at origination typically 40-85% for CRE (see ml/scoring/valuation_discount.py).
    origination = date.today() - timedelta(days=random.randint(180, 8 * 365))
    outstanding = round(value * random.uniform(0.40, 0.85), 2)
    # Real EU Taxonomy classification (ml/regulatory/eu_taxonomy_classifier.py). Physical-risk
    # bucket isn't known yet at seed time (scoring happens after insert) -- the DNSH-adaptation
    # diagnostic that depends on it is filled in by scripts/recompute_taxonomy_status.py once
    # the loan book has been scored, not fabricated here.
    tax = classify_taxonomy(nace)
    return {
        "asset_id": str(uuid.uuid4()), "org_id": DEMO_ORG,
        "asset_name": name_override or f"{region} {sector.split(' ')[0]} {random.randint(1, 99)}",
        "asset_type": atype, "latitude": round(lat, 5), "longitude": round(lon, 5),
        "h3_cell": h3_cell, "region": region, "country": country,
        "asset_value_eur": value, "annual_revenue_eur": round(value * random.uniform(0.08, 0.22)),
        "construction_year": random.randint(1962, 2019), "expected_lifespan_years": lifespan,
        "sector": sector, "nace_code": nace, "gics_code": gics,
        "taxonomy_status": tax["status"],
        "taxonomy_activity": tax["activity_ref"] or sector, "dnsh": json.dumps(tax["reasoning"]),
        "energy_mwh": round(value_m * random.uniform(40, 160)),
        "s1": scope1, "s2": round(scope1 * random.uniform(0.3, 0.8), 1),
        "s3": round(scope1 * random.uniform(1.5, 4.0), 1),
        "outstanding_loan_balance_eur": outstanding, "loan_origination_date": origination.isoformat(),
    }


def main():
    with get_session() as s:
        # keep only land cells — assets in the Mediterranean are not real loans
        flood = [c for c in scored_cells(s, "flood", 336) if on_land(c)]            # Valencia — up to VH
        wildfire = [c for c in random.sample(scored_cells(s, "wildfire", 8000), 2000) if on_land(c)]  # EU — low/med
        assets = []
        # 55 in flood cells (real high risk), 30 in wildfire cells, 40 in financial centres
        for c in random.sample(flood, min(55, len(flood))):
            lat, lon = h3.cell_to_latlng(c)
            assets.append(make_asset(lat, lon, c, "Valencia"))
        for c in random.sample(wildfire, min(30, len(wildfire))):
            lat, lon = h3.cell_to_latlng(c)
            assets.append(make_asset(lat, lon, c, country_for(lat, lon)))
        for _ in range(40):
            name, lat, lon = random.choice(CITIES)
            for _try in range(20):  # jitter, but keep it on land
                jlat, jlon = lat + random.uniform(-0.08, 0.08), lon + random.uniform(-0.08, 0.08)
                if globe.is_land(jlat, jlon):
                    break
            else:
                jlat, jlon = lat, lon
            assets.append(make_asset(jlat, jlon, h3.latlng_to_cell(jlat, jlon, 8), name))
        for name, sector, glat, glon, region in GUATEMALA_ASSETS:
            assets.append(make_asset(glat, glon, h3.latlng_to_cell(glat, glon, 8), region,
                                      force_sector=sector, name_override=name))
        for name, sector, plat, plon, region in PUERTO_RICO_ASSETS:
            assets.append(make_asset(plat, plon, h3.latlng_to_cell(plat, plon, 8), region,
                                      force_sector=sector, name_override=name))

        s.execute(text("""
            INSERT INTO organizations (org_id, name, type, country, aum_eur, employees, created_at, updated_at)
            VALUES (:o, 'Meridian Bank (demo)', 'bank', 'ES', :aum, 4200, now(), now())
            ON CONFLICT (org_id) DO NOTHING
        """), {"o": DEMO_ORG, "aum": 48_000_000_000})
        # portfolio_entities/ext_banking (see b9c0d1e2f3a4 migration) -- the
        # unified schema banking now shares with real estate/asset management,
        # replacing bank_assets/bank_asset_valuations directly.
        s.execute(text("DELETE FROM portfolio_entities WHERE org_id = :o AND vertical = 'banking'"), {"o": DEMO_ORG})
        s.execute(text("""
            INSERT INTO portfolio_entities
                (entity_id, org_id, vertical, entity_name, entity_type, latitude, longitude, h3_cell,
                 region, country, primary_value_eur, sector, nace_code, construction_type, year_built,
                 number_of_stories)
            VALUES
                (:asset_id, :org_id, 'banking', :asset_name, :asset_type, :latitude, :longitude, :h3_cell,
                 :region, :country, :asset_value_eur, :sector, :nace_code, NULL, :construction_year, NULL)
        """), assets)
        s.execute(text("""
            INSERT INTO ext_banking
                (entity_id, annual_revenue_eur, expected_lifespan_years, gics_code, taxonomy_status,
                 taxonomy_activity, dnsh_assessment, energy_consumption_mwh,
                 ghg_emissions_scope1_tco2e, ghg_emissions_scope2_tco2e, ghg_emissions_scope3_tco2e,
                 outstanding_loan_balance_eur, loan_origination_date)
            VALUES
                (:asset_id, :annual_revenue_eur, :expected_lifespan_years, :gics_code, :taxonomy_status,
                 :taxonomy_activity, CAST(:dnsh AS jsonb), :energy_mwh, :s1, :s2, :s3,
                 :outstanding_loan_balance_eur, :loan_origination_date)
        """), assets)
        total = sum(a["asset_value_eur"] for a in assets)
        print(f"seeded {len(assets)} assets, total book €{total/1e9:.2f}bn, org {DEMO_ORG}")
        scored = s.execute(text("""
            SELECT count(DISTINCT e.entity_id) FROM portfolio_entities e
            JOIN canonical_scores cs ON cs.h3_cell = e.h3_cell AND cs.valid_to IS NULL
            WHERE e.org_id = :o AND e.vertical = 'banking'
        """), {"o": DEMO_ORG}).scalar()
        print(f"{scored} of {len(assets)} assets fall in scored cells (rest = no_canonical_score)")


if __name__ == "__main__":
    main()
