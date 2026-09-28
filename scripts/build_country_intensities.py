"""Build the sovereign GHG-intensity table (SFDR PAI 15) from cited public data, on the basis the RTS defines.

SFDR RTS (EU) 2022/1288 Annex I, Table 1, indicator 15 — "GHG intensity of investee countries" — is tonnes of
CO2-equivalent per million EUR of GDP. So for each country, ONE year for both sides:

    intensity = total GHG emissions, excl. land use (Mt CO2e)  × 1e6        (the country's OFFICIAL national inventory
                                                                            as reported to the UNFCCC — Eurostat
                                                                            env_air_gge TOTX4_MEMO — where Eurostat
                                                                            carries it; else OWID total_ghg_excluding_lucf)
              ÷ GDP at current market prices in EUR millions                (World Bank WDI NY.GDP.MKTP.CD, current US$,
                                                                            × that year's average EUR per USD, ECB)

Until 2026-09-27 this divided CO2 ONLY by PPP GDP in constant international dollars — neither CO2e nor euro GDP; the
error ran both ways by country (PPP inflates the GDP of lower-price economies).

The official inventory takes precedence (checked 2026-09-28: OWID's series, which leaves out F-gases, was 5–19% below
the inventories — France 307 vs 378 Mt for 2023). The year is the latest one with GHG, GDP and a full year of ECB
rates for that country; each row says which emissions source it used. Writes
data/reference/country_ghg_intensity.csv with every input, so each figure can be recomputed by hand:
    python -m scripts.build_country_intensities
"""
from __future__ import annotations

import csv
import io
from datetime import date
from pathlib import Path

import requests

EUROSTAT_GGE = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/env_air_gge?format=JSON&lang=en"
                "&unit=MIO_T&airpol=GHG&src_crf=TOTX4_MEMO&sinceTimePeriod=2015")
_EUROSTAT_GEO = {"EL": "GR", "UK": "GB"}
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


def _official_inventories() -> dict[tuple[str, int], float]:
    """(ISO-2, year) → Mt CO2e excl. LULUCF from the national inventories Eurostat publishes (env_air_gge)."""
    d = requests.get(EUROSTAT_GGE, timeout=180).json()
    geos, times = list(d["dimension"]["geo"]["category"]["index"]), list(d["dimension"]["time"]["category"]["index"])
    out = {}
    for gi, g in enumerate(geos):
        if len(g) != 2:                       # EU27_2020 etc.
            continue
        for ti, y in enumerate(times):
            v = d["value"].get(str(gi * len(times) + ti))
            if v is not None:
                out[(_EUROSTAT_GEO.get(g, g), int(y))] = float(v)
    return out


def build() -> int:
    official = _official_inventories()
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
        def emissions(y):
            if (iso2, y) in official:
                return official[(iso2, y)], "national inventory (UNFCCC, via Eurostat env_air_gge)"
            if (iso3, y) in ghg and ghg[(iso3, y)] > 0:
                return ghg[(iso3, y)], "OWID total_ghg_excluding_lucf"
            return None
        years = [y for y in fx if (iso3, y) in gdp and emissions(y)]
        if not years:
            continue
        # prefer the latest year the official inventory covers, if the country has one
        off_years = [y for y in years if (iso2, y) in official]
        y = max(off_years or years)
        mt, src = emissions(y)
        gdp_meur = gdp[(iso3, y)] * fx[y] / 1e6
        rows.append([iso2, round(mt * 1e6 / gdp_meur, 1), y, round(mt, 3), round(gdp_meur, 1),
                     round(fx[y], 6), BASIS, f"{src}; World Bank WDI NY.GDP.MKTP.CD; ECB USD annual average"])

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
