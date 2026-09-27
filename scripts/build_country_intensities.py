"""Build the sovereign GHG-intensity table (SFDR PAI 15) from cited public data, on the basis the RTS defines.

SFDR RTS (EU) 2022/1288 Annex I, Table 1, indicator 15 — "GHG intensity of investee countries" — is tonnes of
CO2-equivalent per million EUR of GDP. So for each country, ONE year for both sides:

    intensity = total GHG emissions, excl. land use (Mt CO2e)  × 1e6        (OWID: total_ghg_excluding_lucf, CO2e)
              ÷ GDP at current market prices in EUR millions                (World Bank WDI NY.GDP.MKTP.CD, current US$,
                                                                            × that year's average EUR per USD, ECB)

Until 2026-09-27 this divided CO2 ONLY by PPP GDP in constant international dollars — neither CO2e nor euro GDP; the
error ran both ways by country (PPP inflates the GDP of lower-price economies).

The year is the latest one with GHG, GDP and a full year of ECB rates for that country. Writes
data/reference/country_ghg_intensity.csv with every input, so each figure can be recomputed by hand:
    python -m scripts.build_country_intensities
"""
from __future__ import annotations

import csv
import io
from datetime import date
from pathlib import Path

import requests

OWID_URL = "https://nyc3.digitaloceanspaces.com/owid-public/data/co2/owid-co2-data.csv"
WB_URL = "https://api.worldbank.org/v2/country/all/indicator/NY.GDP.MKTP.CD?format=json&per_page=20000&date=2015:2030"
OUT = Path(__file__).resolve().parent.parent / "data" / "reference" / "country_ghg_intensity.csv"
BASIS = "total GHG excl. LULUCF (t CO2e) ÷ GDP at current market prices (EUR M), same year"
SOURCE = ("OWID total_ghg_excluding_lucf (Jones et al. / PRIMAP-hist); World Bank WDI NY.GDP.MKTP.CD; "
          "ECB euro reference rate USD, annual average")


def _eur_per_usd_by_year() -> dict[int, float]:
    """Annual average EUR per USD from the platform's ECB rates (full years only)."""
    from core.db.session import get_session
    from services.reference.fx import FxError, average_rate
    out = {}
    with get_session() as s:
        for y in range(2015, date.today().year):
            try:
                out[y] = 1.0 / average_rate(s, "USD", date(y, 1, 1), date(y, 12, 31))["units_per_eur"]
            except FxError:
                continue
    return out


def build() -> int:
    owid = requests.get(OWID_URL, timeout=120)
    owid.raise_for_status()
    ghg: dict[tuple[str, int], float] = {}
    for row in csv.DictReader(io.StringIO(owid.text)):
        iso3, v, y = row.get("iso_code") or "", row.get("total_ghg_excluding_lucf"), row.get("year")
        if len(iso3) == 3 and v and y:
            try:
                ghg[(iso3, int(y))] = float(v)
            except ValueError:
                continue

    _, wb = requests.get(WB_URL, timeout=120).json()
    gdp: dict[tuple[str, int], float] = {}
    iso2_of: dict[str, str] = {}
    for r in wb:
        iso3, iso2 = r.get("countryiso3code") or "", (r.get("country") or {}).get("id") or ""
        if len(iso3) == 3 and len(iso2) == 2 and r.get("value"):
            gdp[(iso3, int(r["date"]))] = float(r["value"])
            iso2_of[iso3] = iso2

    fx = _eur_per_usd_by_year()
    rows = []
    for iso3, iso2 in sorted(iso2_of.items(), key=lambda kv: kv[1]):
        years = [y for y in fx if (iso3, y) in ghg and (iso3, y) in gdp and ghg[(iso3, y)] > 0]
        if not years:
            continue
        y = max(years)
        gdp_meur = gdp[(iso3, y)] * fx[y] / 1e6
        rows.append([iso2, round(ghg[(iso3, y)] * 1e6 / gdp_meur, 1), y, round(ghg[(iso3, y)], 3), round(gdp_meur, 1),
                     round(fx[y], 6), BASIS, SOURCE])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["country_iso2", "intensity_tco2e_per_meur", "gdp_year", "ghg_mt_co2e", "gdp_meur", "eur_per_usd",
                    "basis", "source"])
        w.writerows(rows)
    print(f"wrote {len(rows)} countries → {OUT}")
    return len(rows)


if __name__ == "__main__":
    build()
