"""Build the US GDP deflator table used to state NGFS carbon prices in today's money.

NGFS publishes scenario carbon prices in constant 2010 US dollars (US$2010/tCO2). To apply them to a company's
revenue in a reporting year, the price is first brought to that year's dollars with the US GDP implicit price deflator
(World Bank WDI NY.GDP.DEFL.ZS, United States, 2020 = 100), then converted to the figures' currency at that year's
average rate (services/reference/carbon_price.py).

Writes data/reference/us_gdp_deflator.csv (year, deflator, source, retrieved). Re-run yearly to refresh:
    python -m scripts.build_us_gdp_deflator
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import requests

URL = "https://api.worldbank.org/v2/country/USA/indicator/NY.GDP.DEFL.ZS?format=json&per_page=200&date=2000:2100"
OUT = Path(__file__).resolve().parent.parent / "data" / "reference" / "us_gdp_deflator.csv"
SOURCE = "World Bank WDI NY.GDP.DEFL.ZS (United States, GDP implicit price deflator, 2020=100)"


def main() -> None:
    meta, rows = requests.get(URL, timeout=60).json()
    series = sorted((int(r["date"]), float(r["value"])) for r in rows if r.get("value") is not None)
    if not any(y == 2010 for y, _ in series):
        raise SystemExit("the 2010 base year is missing from the World Bank response — refusing to write")
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "deflator", "source", "retrieved", "wdi_last_updated"])
        for y, v in series:
            w.writerow([y, round(v, 6), SOURCE, date.today().isoformat(), meta.get("lastupdated")])
    print(f"wrote {len(series)} years ({series[0][0]}–{series[-1][0]}) to {OUT}")


if __name__ == "__main__":
    main()
