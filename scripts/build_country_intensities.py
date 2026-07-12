"""Build the sovereign GHG-intensity table from real, cited open data.

Sovereign PAI 15 (GHG intensity of investee countries) needs a per-country
tCO2e-per-€M-GDP figure. This computes it from Our World in Data's CO2 dataset
(Global Carbon Project emissions + GDP), rather than the illustrative placeholders
we shipped first:

    intensity(country) = latest-year CO2 (tonnes) ÷ GDP (€M)   [PPP int-$ ≈ €M]

Writes data/reference/country_ghg_intensity.csv with a source + vintage column so
the figure is auditable. Re-run to refresh:  python -m scripts.build_country_intensities

Note: OWID GDP is PPP int-$; for a market-EUR denominator, swap in World Bank
NY.GDP.MKTP.CD (api.worldbank.org). Flagged, not hidden.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

import requests

OWID_URL = "https://nyc3.digitaloceanspaces.com/owid-public/data/co2/owid-co2-data.csv"
OUT = Path(__file__).resolve().parent.parent / "data" / "reference" / "country_ghg_intensity.csv"

# ISO-3 → ISO-2 for the countries we hold / commonly encounter (issuers store ISO-2).
ISO3_TO_ISO2 = {
    "DEU": "DE", "FRA": "FR", "NLD": "NL", "ESP": "ES", "ITA": "IT", "SWE": "SE",
    "DNK": "DK", "NOR": "NO", "FIN": "FI", "GBR": "GB", "CHE": "CH", "BEL": "BE",
    "AUT": "AT", "IRL": "IE", "PRT": "PT", "POL": "PL", "GRC": "GR", "LUX": "LU",
    "CZE": "CZ", "USA": "US", "JPN": "JP", "CHN": "CN", "IND": "IN", "ZAF": "ZA",
    "RUS": "RU", "AUS": "AU", "BRA": "BR", "CAN": "CA", "KOR": "KR", "MEX": "MX",
    "TUR": "TR", "IDN": "ID", "SAU": "SA", "HUN": "HU", "ROU": "RO", "SVK": "SK",
    "SVN": "SI", "HRV": "HR", "BGR": "BG", "LTU": "LT", "LVA": "LV", "EST": "EE",
}


def build() -> int:
    resp = requests.get(OWID_URL, timeout=60)
    resp.raise_for_status()
    reader = csv.DictReader(io.StringIO(resp.text))

    # keep the latest year per country that has BOTH co2 (Mt) and gdp.
    latest: dict[str, dict] = {}
    for row in reader:
        iso2 = ISO3_TO_ISO2.get(row.get("iso_code", ""))
        if not iso2:
            continue
        co2, gdp, year = row.get("co2"), row.get("gdp"), row.get("year")
        if not (co2 and gdp and year):
            continue
        try:
            co2_mt, gdp_v, yr = float(co2), float(gdp), int(year)
        except ValueError:
            continue
        if gdp_v <= 0 or co2_mt <= 0:
            continue
        if iso2 not in latest or yr > latest[iso2]["year"]:
            # tCO2e per €M GDP  =  (Mt × 1e6 tonnes) / (GDP / 1e6)
            latest[iso2] = {"year": yr, "intensity": round(co2_mt * 1e12 / gdp_v, 1)}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["country_iso2", "intensity_tco2e_per_meur", "gdp_year", "source"])
        for iso2 in sorted(latest):
            d = latest[iso2]
            w.writerow([iso2, d["intensity"], d["year"],
                        "OWID (Global Carbon Project CO2 ÷ GDP, PPP int-$)"])
    print(f"wrote {len(latest)} countries → {OUT}")
    return len(latest)


if __name__ == "__main__":
    build()
