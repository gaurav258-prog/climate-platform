"""Build a "near real" loan book against the ING Bank N.V. (mirror) entity tree.

Two real, disclosed numbers anchor this — everything else is disclosed as a modelled allocation, never
passed off as ING's actual counterparty-level data (which is confidential and was never available):

1. Note 7 "Loans and advances to customers by type" (ING Bank Annual Report 2025) — the REAL, exact GROSS
   book split by product AND by Netherlands vs. Rest-of-world, EUR million:

       product                  Netherlands   Rest of world      Total
       Public authorities             3,452          19,583     23,034
       Residential mortgages        126,772         242,297    369,069
       Other personal lending         5,033          34,690     39,723
       Corporate Lending             68,866         226,981    295,847
       TOTAL                        204,122         523,551    727,673

2. The "Additional information by country" CRD IV Art. 89 table (same annual report) — REAL total-assets
   per country for every entity in the tree (already used to build the tree itself in
   scripts/seed_ing_org_structure.py).

Methodology (disclosed, not hidden):
  - The Netherlands total (EUR 204,122m) is split 95% to the "Netherlands (head office)" entity and 5% of
    its Corporate Lending slice to ING Commercial Finance B.V. — a real ING subsidiary whose actual business
    (factoring/commercial finance) is corporate-lending-adjacent; ING does not disclose the exact split, so
    this ratio is a stated modelling assumption, not a reported figure.
  - The Rest-of-world total (EUR 523,551m) is allocated across every foreign entity PROPORTIONALLY to that
    entity's own real, disclosed total-assets share of the combined foreign total-assets in the CbCR table.
    This is the most defensible real-data-grounded split available without ING's internal segment data.
  - Within each entity's allocated total, the product-type MIX uses the real NL or real RoW ratios from
    Note 7 (NL entities get the NL mix, foreign entities get the RoW mix) — never a per-entity mix, since
    ING doesn't disclose one.
  - Individual loan ROWS within an (entity, product) bucket are synthetic — sized with a realistic
    distribution for that product (many small mortgages, fewer large corporate loans) and geolocated with a
    small jitter around real cities in that entity's country — but their sum is engineered to match the
    allocated total above. No single row represents a real ING loan or borrower.
  - ING Hubs B.V. (a global-services entity, not a lender) and the TMBThanachart Bank associate (equity
    method — ING does not control it, so it is never line-by-line consolidated) both correctly get ZERO
    loan-book rows, matching real accounting treatment, not an oversight.

counterparty_evic_eur is a REQUIRED ingestion field (used for PCAF financed-emissions attribution, which is
only methodologically meaningful for corporate exposures). For mortgages/personal/public-authority rows —
where EVIC-based attribution doesn't apply — it is set equal to the exposure itself, satisfying the schema
without implying a real EVIC figure; corporate rows get a genuine EVIC proxy (3-6x the loan, a plausible
leverage multiple), still explicitly a modelled estimate, never a real market figure.

Usage:  .venv/bin/python -m scripts.seed_ing_loan_book
Requires scripts/seed_ing_org_structure.py to have been run first.
"""
from __future__ import annotations

import random

from core.db.session import get_session
from services.ingest.portfolio_ingest import ingest_bank_assets
from sqlalchemy import text

random.seed(20260923)   # reproducible

ORG_NAME = "ING Bank N.V. (mirror)"

# Real Note 7 gross figures (EUR million) -> EUR.
NL_MIX = {"public": 3_452e6, "mortgage": 126_772e6, "personal": 5_033e6, "corporate": 68_866e6}
ROW_MIX = {"public": 19_583e6, "mortgage": 242_297e6, "personal": 34_690e6, "corporate": 226_981e6}

# entity name (as created by seed_ing_org_structure.py) -> real CbCR total-assets EUR million, for foreign
# entities only (drives the proportional RoW allocation). Netherlands itself is handled separately below.
FOREIGN_TOTAL_ASSETS_EURM = {
    "ING België N.V. (BE)": 137_150,
    "ING Luxembourg S.A. (LU)": 14_104,
    "ING-DiBa AG (DE)": 182_899,
    "ING Bank Śląski S.A. (PL)": 61_344,
    "ING Financial Holdings Corporation (US)": 61_483,
    "ING Bank A.Ş. (TR)": 4_958,
    "ING Bank (Australia) Ltd (AU)": 55_976,
    "ING Bank (Eurasia) Z.A.O. (RU)": 1_086,
    "PJSC ING Bank Ukraine (UA)": 567,
    "ING ADMINISTRAÇÃO LTDA. (BR)": 55,
    "ING Consulting, S.A. de C.V. (MX)": 1,   # effectively nil — in run-off
    "Branch of ING Bank N.V. — Spain": 38_559,
    "Branch of ING Bank N.V. — Italy": 20_313,
    "Branch of ING Bank N.V. — Romania": 14_151,
    "Branch of ING Bank N.V. — United Kingdom": 63_746,
    "Branch of ING Bank N.V. — Switzerland": 9_641,
    "Branch of ING Bank N.V. — France": 7_780,
    "Branch of ING Bank N.V. — Ireland": 4_047,
    "Branch of ING Bank N.V. — Czech Republic": 3_561,
    "Branch of ING Bank N.V. — Hungary": 2_183,
    "Branch of ING Bank N.V. — Slovakia": 686,
    "Branch of ING Bank N.V. — Portugal": 714,
    "Branch of ING Bank N.V. — Bulgaria": 611,
    "Branch of ING Bank N.V. — Austria": 845,
    "Branch of ING Bank N.V. — Singapore": 38_414,
    "Branch of ING Bank N.V. — Japan": 7_401,
    "Branch of ING Bank N.V. — South Korea": 8_343,
    "Branch of ING Bank N.V. — Hong Kong": 3_469,
    "Branch of ING Bank N.V. — Taiwan": 6_054,
    "Branch of ING Bank N.V. — China": 1_129,
    "Branch of ING Bank N.V. — Philippines": 496,
    "Branch of ING Bank N.V. — United Arab Emirates": 1,
    "Branch of ING Hubs B.V. — Sri Lanka": 2,
}
# Entities that correctly get NO loan book: ING Hubs B.V. (global services, not a lender) and the
# TMBThanachart Bank associate (equity method — not consolidated line-by-line). Never silently included.
NO_BOOK = {"ING Hubs B.V. (NL)", "TMBThanachart Bank Public Company Ltd (TH)"}

# Real anchor cities (lat, lon) per country, for realistic geographic spread — NOT real borrower addresses.
CITIES = {
    "NL": [("Amsterdam", 52.3676, 4.9041), ("Rotterdam", 51.9244, 4.4777), ("Utrecht", 52.0907, 5.1214)],
    "BE": [("Brussels", 50.8503, 4.3517), ("Antwerp", 51.2194, 4.4025)],
    "LU": [("Luxembourg City", 49.6116, 6.1319)],
    "DE": [("Frankfurt", 50.1109, 8.6821), ("Munich", 48.1351, 11.5820), ("Berlin", 52.5200, 13.4050)],
    "PL": [("Katowice", 50.2649, 19.0238), ("Warsaw", 52.2297, 21.0122)],
    "US": [("New York", 40.7128, -74.0060), ("Wilmington DE", 39.7391, -75.5398)],
    "TR": [("Istanbul", 41.0082, 28.9784)],
    "AU": [("Sydney", -33.8688, 151.2093), ("Melbourne", -37.8136, 144.9631)],
    "RU": [("Moscow", 55.7558, 37.6173)],
    "UA": [("Kyiv", 50.4501, 30.5234)],
    "BR": [("São Paulo", -23.5505, -46.6333)],
    "MX": [("Mexico City", 19.4326, -99.1332)],
    "ES": [("Madrid", 40.4168, -3.7038), ("Barcelona", 41.3874, 2.1686)],
    "IT": [("Milan", 45.4642, 9.1900), ("Rome", 41.9028, 12.4964)],
    "RO": [("Bucharest", 44.4268, 26.1025)],
    "GB": [("London", 51.5074, -0.1278)],
    "CH": [("Zurich", 47.3769, 8.5417)],
    "FR": [("Paris", 48.8566, 2.3522)],
    "IE": [("Dublin", 53.3498, -6.2603)],
    "CZ": [("Prague", 50.0755, 14.4378)],
    "HU": [("Budapest", 47.4979, 19.0402)],
    "SK": [("Bratislava", 48.1486, 17.1077)],
    "PT": [("Lisbon", 38.7223, -9.1393)],
    "BG": [("Sofia", 42.6977, 23.3219)],
    "AT": [("Vienna", 48.2082, 16.3738)],
    "SG": [("Singapore", 1.3521, 103.8198)],
    "JP": [("Tokyo", 35.6762, 139.6503)],
    "KR": [("Seoul", 37.5665, 126.9780)],
    "HK": [("Hong Kong", 22.3193, 114.1694)],
    "TW": [("Taipei", 25.0330, 121.5654)],
    "CN": [("Shanghai", 31.2304, 121.4737)],
    "PH": [("Manila", 14.5995, 120.9842)],
    "AE": [("Dubai", 25.2048, 55.2708)],
    "LK": [("Colombo", 6.9271, 79.8612)],
}
# entity name -> ISO-2 (for the CITIES lookup + the country field on each loan)
ENTITY_COUNTRY = {
    "ING België N.V. (BE)": "BE", "ING Luxembourg S.A. (LU)": "LU", "ING-DiBa AG (DE)": "DE",
    "ING Bank Śląski S.A. (PL)": "PL", "ING Financial Holdings Corporation (US)": "US",
    "ING Bank A.Ş. (TR)": "TR", "ING Bank (Australia) Ltd (AU)": "AU",
    "ING Bank (Eurasia) Z.A.O. (RU)": "RU", "PJSC ING Bank Ukraine (UA)": "UA",
    "ING ADMINISTRAÇÃO LTDA. (BR)": "BR", "ING Consulting, S.A. de C.V. (MX)": "MX",
    "ING Commercial Finance B.V. (NL)": "NL",
    "Branch of ING Bank N.V. — Spain": "ES", "Branch of ING Bank N.V. — Italy": "IT",
    "Branch of ING Bank N.V. — Romania": "RO", "Branch of ING Bank N.V. — United Kingdom": "GB",
    "Branch of ING Bank N.V. — Switzerland": "CH", "Branch of ING Bank N.V. — France": "FR",
    "Branch of ING Bank N.V. — Ireland": "IE", "Branch of ING Bank N.V. — Czech Republic": "CZ",
    "Branch of ING Bank N.V. — Hungary": "HU", "Branch of ING Bank N.V. — Slovakia": "SK",
    "Branch of ING Bank N.V. — Portugal": "PT", "Branch of ING Bank N.V. — Bulgaria": "BG",
    "Branch of ING Bank N.V. — Austria": "AT", "Branch of ING Bank N.V. — Singapore": "SG",
    "Branch of ING Bank N.V. — Japan": "JP", "Branch of ING Bank N.V. — South Korea": "KR",
    "Branch of ING Bank N.V. — Hong Kong": "HK", "Branch of ING Bank N.V. — Taiwan": "TW",
    "Branch of ING Bank N.V. — China": "CN", "Branch of ING Bank N.V. — Philippines": "PH",
    "Branch of ING Bank N.V. — United Arab Emirates": "AE", "Branch of ING Hubs B.V. — Sri Lanka": "LK",
}

_CORP_SECTORS = [("industrial", "Manufacturing", "C"), ("commercial_real_estate", "Real estate", "L"),
                 ("logistics", "Transportation", "H"), ("energy", "Energy & utilities", "D"),
                 ("office", "Wholesale trade", "G"), ("Manufacturing", "Manufacturing", "C")]


def _jitter(lat: float, lon: float, deg: float = 0.6) -> tuple[float, float]:
    return (max(-90, min(90, lat + random.uniform(-deg, deg))),
            max(-180, min(180, lon + random.uniform(-deg, deg))))


def _split_rows(total_eur: float, n: int, lo_mult: float, hi_mult: float) -> list[float]:
    """n positive row sizes (a lognormal-ish spread between lo_mult..hi_mult of the mean) that sum exactly
    to total_eur (the last row absorbs the rounding remainder)."""
    if n <= 0 or total_eur <= 0:
        return []
    mean = total_eur / n
    raw = [mean * random.uniform(lo_mult, hi_mult) for _ in range(n)]
    scale = total_eur / sum(raw)
    sizes = [r * scale for r in raw]
    sizes[-1] += total_eur - sum(sizes)   # exact tie-out
    return sizes


def _rows_for_bucket(entity_name: str, country: str, product: str, total_eur: float) -> list[dict]:
    if total_eur <= 0:
        return []
    cities = CITIES.get(country, [("", 0.0, 0.0)])
    rows: list[dict] = []

    if product == "mortgage":
        # many smaller loans; row count scales with size, capped for demo practicality.
        # appraised_value_eur MUST equal the allocated loan exposure itself (Tellumen reports book totals
        # from appraised_value_eur, and Note 7's real figure is the loan BALANCE, not the underlying
        # property's market value, which ING doesn't disclose and would otherwise silently inflate the
        # reported book above the real disclosed total — a real bug caught by checking the tie-out after
        # the first run). outstanding_loan_balance_eur is set fractionally lower to keep the optional
        # LTV-derived metrics sane without implying a genuine, separately-sourced property valuation.
        n = max(3, min(40, round(total_eur / 25_000_000)))
        for i, amt in enumerate(_split_rows(total_eur, n, 0.4, 2.2)):
            city, lat, lon = random.choice(cities)
            jlat, jlon = _jitter(lat, lon)
            rows.append({"asset_name": f"{entity_name.split(' (')[0]} residential mortgage pool {i+1} ({city})",
                        "asset_type": "residential_real_estate", "sector": "Residential mortgages",
                        "latitude": jlat, "longitude": jlon, "appraised_value_eur": round(amt, 2),
                        "outstanding_loan_balance_eur": round(amt * random.uniform(0.75, 0.95), 2),
                        "counterparty_evic_eur": round(amt, 2), "region": city, "country": country})
    elif product == "personal":
        n = max(2, min(15, round(total_eur / 60_000_000)))
        for i, amt in enumerate(_split_rows(total_eur, n, 0.5, 1.8)):
            city, lat, lon = random.choice(cities)
            jlat, jlon = _jitter(lat, lon)
            rows.append({"asset_name": f"{entity_name.split(' (')[0]} consumer lending pool {i+1} ({city})",
                        "asset_type": "loan", "sector": "Consumer lending",
                        "latitude": jlat, "longitude": jlon, "appraised_value_eur": round(amt, 2),
                        "outstanding_loan_balance_eur": round(amt, 2), "counterparty_evic_eur": round(amt, 2),
                        "region": city, "country": country})
    elif product == "public":
        n = max(1, min(5, round(total_eur / 500_000_000)))
        for i, amt in enumerate(_split_rows(total_eur, n, 0.6, 1.5)):
            city, lat, lon = random.choice(cities)
            jlat, jlon = _jitter(lat, lon, deg=0.15)
            rows.append({"asset_name": f"{entity_name.split(' (')[0]} public-sector exposure {i+1} ({city})",
                        "asset_type": "loan", "sector": "Public administration",
                        "latitude": jlat, "longitude": jlon, "appraised_value_eur": round(amt, 2),
                        "outstanding_loan_balance_eur": round(amt, 2), "counterparty_evic_eur": round(amt, 2),
                        "region": city, "country": country, "counterparty_govt_level": "central"})
    elif product == "corporate":
        n = max(2, min(20, round(total_eur / 80_000_000)))
        for i, amt in enumerate(_split_rows(total_eur, n, 0.3, 3.0)):
            city, lat, lon = random.choice(cities)
            jlat, jlon = _jitter(lat, lon)
            atype, sector, nace = random.choice(_CORP_SECTORS)
            evic = round(amt * random.uniform(3.0, 6.0), 2)   # a plausible leverage multiple, disclosed as modelled
            rows.append({"asset_name": f"{entity_name.split(' (')[0]} corporate loan {i+1} — {sector} ({city})",
                        "asset_type": atype, "sector": sector,
                        "latitude": jlat, "longitude": jlon, "appraised_value_eur": round(amt, 2),
                        "outstanding_loan_balance_eur": round(amt, 2), "counterparty_evic_eur": evic,
                        "region": city, "country": country})
    return rows


def main() -> None:
    with get_session() as s:
        org_id = s.execute(text("SELECT org_id::text FROM organizations WHERE name = :n"), {"n": ORG_NAME}).scalar()
        if not org_id:
            raise SystemExit(f"'{ORG_NAME}' not found — run scripts/seed_ing_org_structure.py first")
        entities = {r["name"]: r["entity_id"] for r in s.execute(text(
            "SELECT entity_id::text AS entity_id, name FROM reporting_entities WHERE org_id = CAST(:o AS uuid)"),
            {"o": org_id}).mappings().all()}

        total_landed = 0
        total_eur_landed = 0.0

        # ── Netherlands: 95% to the NL head-office entity, 5% of Corporate Lending to Commercial Finance ──
        nl_name = next(n for n in entities if n.startswith("ING Bank N.V. — Netherlands"))
        cf_name = "ING Commercial Finance B.V. (NL)"
        cf_corp = NL_MIX["corporate"] * 0.05
        nl_bucket = {"public": NL_MIX["public"], "mortgage": NL_MIX["mortgage"],
                    "personal": NL_MIX["personal"], "corporate": NL_MIX["corporate"] - cf_corp}
        rows = []
        for product, amt in nl_bucket.items():
            rows.extend(_rows_for_bucket(nl_name, "NL", product, amt))
        res = ingest_bank_assets(s, org_id, rows, reporting_entity_id=entities[nl_name])
        total_landed += res["n_ingested"]; total_eur_landed += sum(r["appraised_value_eur"] for r in rows)
        print(f"{nl_name}: {res['n_ingested']} rows, {res['n_skipped']} skipped, €{sum(r['appraised_value_eur'] for r in rows)/1e9:.2f}bn")

        cf_rows = _rows_for_bucket(cf_name, "NL", "corporate", cf_corp)
        res = ingest_bank_assets(s, org_id, cf_rows, reporting_entity_id=entities[cf_name])
        total_landed += res["n_ingested"]; total_eur_landed += sum(r["appraised_value_eur"] for r in cf_rows)
        print(f"{cf_name}: {res['n_ingested']} rows, {res['n_skipped']} skipped, €{sum(r['appraised_value_eur'] for r in cf_rows)/1e9:.2f}bn")

        # ── Rest of world: proportional to real disclosed total assets per entity ──
        row_total_assets = sum(FOREIGN_TOTAL_ASSETS_EURM.values())
        for entity_name, assets_eurm in FOREIGN_TOTAL_ASSETS_EURM.items():
            if entity_name not in entities:
                print(f"  ! '{entity_name}' not found in tree, skipping"); continue
            if entity_name in NO_BOOK:
                continue
            share = assets_eurm / row_total_assets
            country = ENTITY_COUNTRY[entity_name]
            rows = []
            for product, amt in ROW_MIX.items():
                rows.extend(_rows_for_bucket(entity_name, country, product, amt * share))
            if not rows:
                continue
            res = ingest_bank_assets(s, org_id, rows, reporting_entity_id=entities[entity_name])
            total_landed += res["n_ingested"]; total_eur_landed += sum(r["appraised_value_eur"] for r in rows)
            print(f"{entity_name}: {res['n_ingested']} rows, {res['n_skipped']} skipped, "
                 f"€{sum(r['appraised_value_eur'] for r in rows)/1e9:.2f}bn")

        s.commit()
        print(f"\ndone — {total_landed} loan-book rows landed, €{total_eur_landed/1e9:.1f}bn total "
             f"(real disclosed group total: €727.7bn gross)")


if __name__ == "__main__":
    main()
