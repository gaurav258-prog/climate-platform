"""Build the country renewable-share table used to ESTIMATE a company's non-renewable energy shares (SFDR PAI 5)
when neither the company nor a data vendor gives them.

  consumption  non-renewable share ≈ 100 − the country's renewable share of primary energy   (OWID renewables_share_energy)
  production   non-renewable share ≈ 100 − the country's renewable share of electricity      (OWID renewables_share_elec)
               — used for electricity producers (NACE D), whose production is the country's power mix unless they
                 report their own.

A company's own mix can differ a lot from its country's; the estimate is labelled as such wherever it is used, and a
reported or vendor figure always takes precedence. Latest year with data per country; every input kept per row.
    python -m scripts.build_country_renewable_shares
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

import requests

OWID = "https://nyc3.digitaloceanspaces.com/owid-public/data/energy/owid-energy-data.csv"
WB = "https://api.worldbank.org/v2/country?format=json&per_page=400"
OUT = Path(__file__).resolve().parent.parent / "data" / "reference" / "country_renewable_shares.csv"
SOURCE = "Our World in Data energy dataset (Energy Institute Statistical Review; Ember) — renewables_share_energy / _elec"


def build() -> int:
    _, countries = requests.get(WB, timeout=60).json()
    iso2 = {c["id"]: c["iso2Code"] for c in countries if len(c.get("iso2Code") or "") == 2 and c["region"]["id"] != "NA"}
    latest: dict[str, dict] = {}
    for r in csv.DictReader(io.StringIO(requests.get(OWID, timeout=180).text)):
        code = iso2.get(r.get("iso_code") or "")
        if not code:
            continue
        y = int(r["year"])
        for key, col in (("energy", "renewables_share_energy"), ("elec", "renewables_share_elec")):
            v = r.get(col)
            if v:
                cur = latest.setdefault(code, {})
                if y >= cur.get(f"{key}_year", 0):
                    cur[key], cur[f"{key}_year"] = float(v), y
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["country_iso2", "renewable_share_energy_pct", "energy_year", "renewable_share_elec_pct", "elec_year", "source"])
        for c in sorted(latest):
            d = latest[c]
            w.writerow([c, d.get("energy"), d.get("energy_year"), d.get("elec"), d.get("elec_year"), SOURCE])
    print(f"wrote {len(latest)} countries → {OUT}")
    return len(latest)


if __name__ == "__main__":
    build()
