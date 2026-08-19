"""End-to-end demo: a real EU Article-8 manager onboards a fund and files SFDR.

Runs the ACTUAL product path (the /v1/funds API, not shortcuts) with a realistic
book that deliberately mixes the three data tiers a real manager arrives with:

  * FULLY DISCLOSED  — NACE + revenue + scope 1/2/3 + EVIC  → every carbon
                       indicator computes, incl. financed emissions (PAI 1/2).
  * ESTIMATE-ONLY    — NACE + revenue, no emissions          → emissions estimated
                       from EXIOBASE sector intensity, disclosed as estimated.
  * BARE ISIN        — nothing but the code                  → resolved + located,
                       the rest surfaced as an honest gap.

Plus a fossil-sector name so PAI 4 lights up. It then reads out the SFDR filing
so you can see exactly where a real book lands.

    python -m scripts.demo_asset_manager_walkthrough
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from api.main import app
from core.db.session import get_session

ORG = "44444444-4444-4444-8444-444444444444"       # Nordkap (demo org)
FUND_NAME = "Meridian European Sustainable Leaders (SFDR Art. 8)"

# (isin, market_value_eur, nace, revenue, s1, s2, s3, evic)  — None where the manager lacks it
BOOK = [
    # ── fully disclosed (financed emissions computable) ──
    ("DE0007164600", 55_000_000, "62.01", 31_200_000_000, 30_000, 45_000, 4_300_000, 210_000_000_000),   # SAP
    ("NL0010273215", 60_000_000, "26.11", 27_600_000_000, 90_000, 300_000, 5_000_000, 350_000_000_000),   # ASML
    ("CH0038863350", 45_000_000, "10.86", 93_000_000_000, 700_000, 2_300_000, 90_000_000, 300_000_000_000),  # Nestlé
    ("DK0062498333", 40_000_000, "21.20", 33_000_000_000, 100_000, 130_000, 3_000_000, 450_000_000_000),   # Novo Nordisk
    ("FR0000121014", 35_000_000, "15.20", 86_000_000_000, 90_000, 500_000, 12_000_000, 400_000_000_000),   # LVMH
    # ── estimate-only (NACE + revenue, emissions estimated from EXIOBASE) ──
    ("ES0144580Y14", 40_000_000, "35.11", 49_000_000_000, None, None, None, None),   # Iberdrola (electricity → high)
    ("FR0000120073", 30_000_000, "20.11", 27_000_000_000, None, None, None, None),   # Air Liquide (chemicals)
    ("DE0007664039", 25_000_000, "29.10", 322_000_000_000, None, None, None, None),  # Volkswagen (autos)
    ("FR0000121972", 30_000_000, "27.12", 34_000_000_000, None, None, None, None),   # Schneider (electrical)
    # ── a fossil-sector name (PAI 4 fossil-fuel exposure) ──
    ("FR0000120271", 20_000_000, "06.10", 210_000_000_000, None, None, None, None),  # TotalEnergies (oil & gas)
    # ── bare ISIN (resolve + locate; emissions a disclosed gap) ──
    ("NL0012969182", 25_000_000, None, None, None, None, None, None),  # Adyen
    ("NL0000395903", 20_000_000, None, None, None, None, None, None),  # Wolters Kluwer
    ("DE0005810055", 20_000_000, None, None, None, None, None, None),  # Deutsche Börse
]


# The fully-disclosed names also come with the manager's ESG feed (PAI 5-14).
ESG = {
    "DE0007164600": dict(non_renewable_energy_pct=18, energy_intensity_gwh_per_meur=0.02, biodiversity_sensitive_ops=False, emissions_to_water_tonnes=900, hazardous_waste_tonnes=400, ungc_oecd_violation=False, ungc_oecd_no_monitoring=False, gender_pay_gap_pct=11, board_female_pct=42, controversial_weapons=False),
    "NL0010273215": dict(non_renewable_energy_pct=25, energy_intensity_gwh_per_meur=0.05, biodiversity_sensitive_ops=False, emissions_to_water_tonnes=1500, hazardous_waste_tonnes=2200, ungc_oecd_violation=False, ungc_oecd_no_monitoring=False, gender_pay_gap_pct=14, board_female_pct=38, controversial_weapons=False),
    "CH0038863350": dict(non_renewable_energy_pct=45, energy_intensity_gwh_per_meur=0.15, biodiversity_sensitive_ops=True, emissions_to_water_tonnes=50000, hazardous_waste_tonnes=12000, ungc_oecd_violation=False, ungc_oecd_no_monitoring=False, gender_pay_gap_pct=18, board_female_pct=33, controversial_weapons=False),
    "DK0062498333": dict(non_renewable_energy_pct=12, energy_intensity_gwh_per_meur=0.03, biodiversity_sensitive_ops=False, emissions_to_water_tonnes=600, hazardous_waste_tonnes=800, ungc_oecd_violation=False, ungc_oecd_no_monitoring=False, gender_pay_gap_pct=9, board_female_pct=45, controversial_weapons=False),
    "FR0000121014": dict(non_renewable_energy_pct=30, energy_intensity_gwh_per_meur=0.04, biodiversity_sensitive_ops=False, emissions_to_water_tonnes=2000, hazardous_waste_tonnes=1500, ungc_oecd_violation=False, ungc_oecd_no_monitoring=False, gender_pay_gap_pct=16, board_female_pct=40, controversial_weapons=False),
}


def _holding(row):
    isin, mv, nace, rev, s1, s2, s3, evic = row
    h = {"isin": isin, "market_value_eur": mv, "asset_class": "equity"}
    if nace: h["nace_code"] = nace
    if rev is not None: h["revenue_eur"] = rev
    if s1 is not None: h["scope1_tco2e"] = s1
    if s2 is not None: h["scope2_tco2e"] = s2
    if s3 is not None: h["scope3_tco2e"] = s3
    if evic is not None: h["evic_eur"] = evic
    h["reporting_year"] = 2023
    h.update(ESG.get(isin, {}))
    return h


def run() -> str:
    isins = [x[0] for x in BOOK]
    with get_session() as s:
        s.execute(text("DELETE FROM funds WHERE org_id = :o AND name = :n"), {"o": ORG, "n": FUND_NAME})
        # Clear this org's prior disclosures for the book's issuers so the two-period
        # (FY2022 → FY2023) reference-year detection is clean, not polluted by earlier runs.
        for tbl in ("issuer_emissions", "issuer_esg_metrics"):
            s.execute(text(f"DELETE FROM {tbl} WHERE org_id = :o AND issuer_id IN "
                           "(SELECT issuer_id FROM securities WHERE isin = ANY(:isins))"),
                      {"o": ORG, "isins": isins})
        fund_id = str(s.execute(text(
            "INSERT INTO funds (org_id, name, fund_type, sfdr_classification, base_currency) "
            "VALUES (:o, :n, 'fund', 'article_8', 'EUR') RETURNING fund_id"),
            {"o": ORG, "n": FUND_NAME}).scalar())

    c = TestClient(app)
    print(f"\n═══ {FUND_NAME} ═══")
    print(f"Manager uploads {len(BOOK)} holdings (mixed data availability)…\n")

    def _year(h, year, scale):
        h = dict(h); h["reporting_year"] = year
        for k in ("scope1_tco2e", "scope2_tco2e", "scope3_tco2e"):
            if h.get(k) is not None:
                h[k] = round(h[k] * scale)
        return h

    # Prior reference period (FY2022) — file it so this year has a comparison.
    c.post(f"/v1/funds/{fund_id}/holdings",
           json={"as_of_date": "2026-07-12", "holdings": [_year(_holding(x), 2022, 1.12) for x in BOOK]})
    c.post(f"/v1/funds/{fund_id}/sfdr-statement/file")

    # Current reference period (FY2023).
    r = c.post(f"/v1/funds/{fund_id}/holdings",
               json={"as_of_date": "2026-07-12", "holdings": [_year(_holding(x), 2023, 1.0) for x in BOOK]}).json()
    cov = r["coverage"]
    print("STEP 1 — onboarding (resolve → locate → value-weight)")
    print(f"  match rate        {cov['match_rate_pct']}%  ({cov['matched']}/{r['distinct_isins']} resolved)")
    print(f"  positions created {r['positions_created']}")
    print(f"  footprints        {cov['footprints']['seeded'] + cov['footprints']['already']} located & scored")
    print(f"  issuer data       {cov['client_enriched']['sector']} sector · "
          f"{cov['client_enriched']['emissions']} disclosed · {cov['client_enriched']['estimated']} estimated")
    if cov["unmatched"]:
        print(f"  unmatched         {cov['unmatched']} (surfaced, excluded)")

    st = c.get(f"/v1/funds/{fund_id}/sfdr-statement").json()
    cs = st["coverage_summary"]

    def ind(n):
        return next(i for i in st["indicators"] if i["number"] == n)

    print("\nSTEP 2 — SFDR PAI statement (RTS Annex I) — where it lands")
    print(f"  fund value        €{st['entity']['total_value_eur']/1e6:.0f}m · {st['entity']['positions']} positions · Article 8")
    print(f"  computed          {cs['computed']}/{cs['mandatory_indicators']} mandatory · {cs['partial']} partial · {cs['not_available']} awaiting input")
    p1 = ind(1)["value"]
    print(f"  PAI 1 financed em. scope1+2+3 = {p1['scope_1']:,}/{p1['scope_2']:,}/{p1['scope_3']:,} tCO2e "
          f"[{ind(1)['method']}]")
    print(f"  PAI 2 carbon ftpt  {ind(2)['value']} {ind(2)['unit']} [{ind(2)['method']}]")
    print(f"  PAI 3 WACI         {ind(3)['value']} tCO2e/€m  ({cs['emissions_coverage_pct']}% covered, "
          f"{cs['emissions_estimated_pct']}% of that estimated) [{ind(3)['method']}]")
    print(f"  PAI 4 fossil expo. {ind(4)['value']}% of value [{ind(4)['method']}]")
    if st.get("comparison", {}).get("available"):
        w = ind(3)
        print(f"  YoY vs FY{st['comparison']['prior_reference_year']}: WACI {w.get('prior_value')} → {w['value']} "
              f"({w.get('change_pct')}%) — prior-year comparison from the frozen filing")
    tax = st["taxonomy"]
    print(f"  EU Taxonomy        {tax['assessable_pct']}% assessable · alignment: not asserted (honest)")
    gaps = [ind(n)["number"] for n in range(5, 15) if ind(n)["method"] == "not_available"]
    if gaps:
        print(f"  still needs input  PAI {gaps} (energy/water/waste/social — the manager's next data pull)")
    else:
        print("  still needs input  none — all 14 indicators populated (partial ones show their coverage %)")

    print("\nSTEP 3 — the deliverable")
    print(f"  Download: GET /v1/funds/{fund_id}/sfdr-statement.xlsx  (filing-shaped)")
    print(f"  fund_id = {fund_id}\n")
    return fund_id


if __name__ == "__main__":
    run()
