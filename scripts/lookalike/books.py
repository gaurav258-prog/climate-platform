"""The five lookalike customers' books (the product owner's decisions of 2026-10-23): made-up firms — each name checked
against the GLEIF register to match no company — shaped like real prospects, every asset at a real place
(scripts/lookalike/places.py), every value either an official figure (data/demo/lookalike/prices.json) or an assumption
this module states (ASSUMPTIONS, written beside the files) — never presented as a statistic.

  FIRMS                      who they are: name, sector, home country, the books they send
  rows(firm)                 {template key: [rows in the standard file's field names]}
"""
from __future__ import annotations

import csv
import json

import numpy as np

from scripts.lookalike.places import MIN_BUILT_M2, ROOT, draw

PRICES = ROOT / "data" / "demo" / "lookalike" / "prices.json"
ISSUERS = ROOT / "data" / "universe" / "eu_common_equities.csv"
CROPGRIDS = ROOT / "data" / "datasets" / "derived" / "crop_area_weights" / "extracted" / "CROPGRIDSv1.08_olive.nc"

FIRMS = {
    "weserland": {"name": "Weserland Hypothekenbank", "type": "bank", "country": "DE", "currency": "EUR",
                  "book_date": "2026-06-30", "about": "German mortgage bank: residential mortgages to households"},
    "brezal": {"name": "Brezal Patrimonio SOCIMI", "type": "reit", "country": "ES", "currency": "EUR",
               "book_date": "2026-06-30", "about": "Spanish residential-rental REIT"},
    "skarvholm": {"name": "Skarvholm Försäkring", "type": "insurer", "country": "SE", "currency": "SEK",
                  "book_date": "2025-12-31", "about": "Swedish home insurer"},
    "kestrel": {"name": "Kestrel Ridge Investment Management", "type": "asset_manager", "country": "LU", "currency": "EUR",
                "book_date": "2026-09-30", "about": "manager of an Article 8 European equity fund"},
    "quejigo": {"name": "Olivar del Quejigo", "type": "manufacturer", "country": "ES", "currency": "EUR",
                "book_date": "2025-12-31", "about": "olive-oil producer in Jaén: mills and sourcing plots"},
}

# what no official source gives, stated once — the books use these and nothing else invented
ASSUMPTIONS = {
    "weserland": {"homes": 1000, "appraised_value_eur_by_area_type": {"urban": 480000, "intermediate": 360000, "rural": 290000},
                  "loan_to_value": 0.6,
                  "why": "Germany publishes no official house price level per area (Destatis: index only), so each home's "
                         "value is this stated figure by Eurostat's urban-rural type of its region."},
    "brezal": {"buildings": 60, "floor_m2_per_building": 3200, "net_yield": 0.035,
               "why": "The ministry's appraised value per m² is official; the size of each building and the yield are the "
                      "REIT's stated assumptions."},
    "skarvholm": {"homes": 500, "why": "Each home's building value is Statistics Sweden's 2024 building price per m² "
                                       "(land excluded) times its average floor space per new dwelling — both official; "
                                       "contents are not insured in this book."},
    "kestrel": {"fund": "Kestrel Ridge European Equity", "fund_value_eur": 1200000000, "holdings": 120,
                "why": "Real listed companies by ISIN, equally weighted — the fund's size and weights are stated; no "
                       "figure about any company is made up (their emissions and Taxonomy shares stay gaps)."},
    "quejigo": {"sites": 8, "plots": 120, "plot_area_ha": 15,
                "why": "Each plot's spend is its stated area times Jaén's official 2025 olive yield (dry or irrigated, "
                       "drawn at Jaén's official irrigated share), the official oil per olive, and the official weekly oil "
                       "prices weighted by Jaén's own oil by grade."},
}
URBAN = {1: "urban", 2: "intermediate", 3: "rural"}


def _prices() -> dict:
    return json.loads(PRICES.read_text())


def _urban_type(nuts3: str) -> str:
    from scripts.lookalike.places import _regions
    return URBAN.get(_regions()[nuts3]["properties"].get("URBN_TYPE"), "intermediate")


def weserland() -> dict:
    a = ASSUMPTIONS["weserland"]
    rows = []
    for i, p in enumerate(draw(["DE"], a["homes"], weight="residents", seed=101), start=1):
        value = a["appraised_value_eur_by_area_type"][_urban_type(p.nuts3)]
        rows.append({"external_ref": f"WH-{i:05d}", "asset_name": f"Home loan {i:04d}, {p.region}",
                     "asset_type": "residential_real_estate", "latitude": p.lat, "longitude": p.lon,
                     "appraised_value_eur": value, "outstanding_loan_balance_eur": round(value * a["loan_to_value"]),
                     "sector": "Households", "counterparty_sector": "household", "immovable_collateral": "residential",
                     "occupancy": "residential", "country": "DE", "region": p.region})
    return {"bank_assets": rows}


def brezal() -> dict:
    a, es = ASSUMPTIONS["brezal"], _prices()["es_residential"]["by_nuts3"]
    rows = []
    for i, p in enumerate(draw(sorted(es), a["buildings"], weight="residents", seed=202), start=1):
        value = round(es[p.nuts3]["eur_per_m2"] * a["floor_m2_per_building"])
        rows.append({"external_ref": f"BP-{i:03d}", "property_name": f"Residential building {i:02d}, {p.region}",
                     "latitude": p.lat, "longitude": p.lon, "property_value_eur": value,
                     "annual_noi_eur": round(value * a["net_yield"]), "property_type": "multifamily",
                     "occupancy": "residential", "country": "ES", "region": p.region})
    return {"realestate_properties": rows}


def skarvholm() -> dict:
    a, se = ASSUMPTIONS["skarvholm"], _prices()["se_rebuild"]
    building_sek = round(se["building_price_sek_per_m2"] * se["floor_m2_per_dwelling"])
    rows = [{"external_ref": f"SF-{i:05d}", "policy_name": f"Home {i:04d}, {p.region}", "latitude": p.lat,
             "longitude": p.lon, "building_value_eur": building_sek, "sum_insured_eur": building_sek, "currency": "SEK",
             "occupancy": "residential", "policy_type": "property", "country": "SE", "region": p.region}
            for i, p in enumerate(draw(["SE"], a["homes"], weight="residents", seed=303), start=1)]
    return {"insurance_policies": rows}


def kestrel() -> dict:
    a = ASSUMPTIONS["kestrel"]
    from services.ingest.fund_books import isin_ok
    issuers = [r for r in csv.DictReader(ISSUERS.open()) if isin_ok(r["isin"])]
    rng = np.random.default_rng(404)
    pick = sorted(rng.choice(len(issuers), size=a["holdings"], replace=False))
    each = round(a["fund_value_eur"] / a["holdings"])
    funds = [{"fund_name": a["fund"], "fund_type": "fund", "sfdr_classification": "article_8", "base_currency": "EUR"}]
    holdings = [{"fund_name": a["fund"], "isin": issuers[i]["isin"], "market_value_eur": each,
                 "book_date": FIRMS["kestrel"]["book_date"], "asset_class": "equity"} for i in pick]
    return {"funds": funds, "fund_holdings": holdings}


def _olive_cells(n: int, seed: int) -> list[tuple[float, float]]:
    """Plot locations in Jaén: the centres of the 0.05° CROPGRIDS cells with the most olive area there (the top quarter),
    drawn by that area — never a centre on a built-up 100 m cell (GHSL). Precise to the grid cell, not to a parcel: no
    parcel map is on disk (SIGPAC was not fetched)."""
    import xarray as xr
    from shapely.geometry import Point, shape

    from scripts.lookalike.places import _regions, built_m2_at
    jaen = shape(_regions()["ES616"]["geometry"])
    lo, la, hi_lo, hi_la = jaen.bounds
    ds = xr.open_dataset(CROPGRIDS)["croparea"].sel(lat=slice(la, hi_la), lon=slice(lo, hi_lo)).load()
    cells = [(round(float(y), 4), round(float(x), 4), float(ds.sel(lat=y, lon=x))) for y in ds.lat.values for x in ds.lon.values]
    cells = [c for c in cells if c[2] > 0 and jaen.contains(Point(c[1], c[0]))]
    floor = float(np.percentile([c[2] for c in cells], 75))
    cells = [c for c in cells if c[2] >= floor and built_m2_at(c[0], c[1]) < MIN_BUILT_M2]
    w = np.array([c[2] for c in cells])
    idx = np.random.default_rng(seed).choice(len(cells), size=min(n, len(cells)), replace=False, p=w / w.sum())
    return [cells[i][:2] for i in sorted(idx)]


def quejigo() -> dict:
    a, o = ASSUMPTIONS["quejigo"], _prices()["olive_jaen"]
    kinds = ["factory", "factory", "factory", "warehouse", "warehouse", "hq", "office", "other"]
    names = ["Mill", "Mill", "Bottling plant", "Warehouse", "Warehouse", "Head office", "Office", "Olive yard depot"]
    sites = [{"external_ref": f"OQ-S{i}", "site_name": f"{names[i - 1]} {i}, Jaén", "latitude": p.lat, "longitude": p.lon,
              "site_type": kinds[i - 1], "occupancy": "industrial" if kinds[i - 1] in ("factory", "warehouse") else "commercial",
              "country": "ES", "region": "Jaén"}
             for i, p in enumerate(draw(["ES616"], a["sites"], weight="built", seed=505), start=1)]
    share_irrigated = o["area_irrigated_ha"] / (o["area_irrigated_ha"] + o["area_dry_ha"])
    rng = np.random.default_rng(506)
    price_eur_kg = o["oil_price_eur_per_100kg_jaen_mix"] / 100
    plots = []
    for i, (lat, lon) in enumerate(_olive_cells(a["plots"], 507), start=1):
        irrigated = bool(rng.random() < share_irrigated)
        olive_kg = a["plot_area_ha"] * (o["yield_irrigated_kg_ha"] if irrigated else o["yield_dry_kg_ha"])
        plots.append({"external_ref": f"OQ-P{i:03d}", "plot_name": f"Olive grove {i:03d}, Jaén", "commodity": "Olive oil",
                      "latitude": lat, "longitude": lon, "plot_area_ha": a["plot_area_ha"],
                      "irrigation_status": "irrigated" if irrigated else "rain_fed",
                      "annual_spend_eur": round(olive_kg * o["oil_per_olive"] * price_eur_kg), "country": "ES",
                      "region": "Jaén"})
    return {"company_sites": sites, "supply_plots": plots}


BUILDERS = {"weserland": weserland, "brezal": brezal, "skarvholm": skarvholm, "kestrel": kestrel, "quejigo": quejigo}


def rows(firm: str) -> dict:
    return BUILDERS[firm]()
