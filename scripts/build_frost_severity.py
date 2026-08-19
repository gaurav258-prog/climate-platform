"""Precompute the regional frost-severity climatology → data/frost_severity/<region>.json.

Frost severity is a yearly climatology (it changes when a new winter's ERA5 lands, not per request),
so we compute it once here and the KRI reads the JSON — no NetCDF load on a dashboard request. Real
computed data with stated provenance; re-run when new frost years are fetched.

Run: .venv/bin/python -m scripts.build_frost_severity
"""
from __future__ import annotations

import json
import os

from ml.features.frost import load_hourly_years
from ml.scoring.frost_extent import DAMAGE_THRESHOLD_C, FROST_MONTHS, frost_extent, severity_band

OUT_DIR = "data/frost_severity"
SEVERE = 0.30  # frozen-area fraction at/above which a winter is a "severe" frost (band boundary)

# region_key → (frost-hourly dir, sub-region bbox (lat_min,lat_max,lon_min,lon_max), label, commodity, country)
REGIONS = {
    "brazil_coffee": {
        "year_dir": "data/era5_baseline/frost_hourly_years",
        "bbox": (-23.0, -20.5, -47.0, -44.5),      # Sul/Sudoeste de Minas — the frost-prone arabica heartland
        "label": "Brazil coffee belt (Sul de Minas)",
        "commodity": "Coffee", "country": "BR",
    },
}


def build(region_key: str, cfg: dict) -> dict:
    ds = load_hourly_years(cfg["year_dir"], region_key)
    series = {}
    for y in range(1991, 2025):
        e = frost_extent(ds, y, cfg["bbox"])
        if e is not None:
            series[y] = e
    if not series:
        raise RuntimeError(f"no frost years on disk for {region_key}")
    latest_year = max(series)
    worst_year = max(series, key=series.get)
    severe_years = sorted(y for y, e in series.items() if e >= SEVERE)
    return {
        "region_key": region_key, "label": cfg["label"],
        "commodity": cfg["commodity"], "country": cfg["country"],
        "bbox": list(cfg["bbox"]), "threshold_c": DAMAGE_THRESHOLD_C, "months": FROST_MONTHS,
        "years_covered": [min(series), max(series)], "n_years": len(series),
        "series": {str(y): series[y] for y in sorted(series)},
        "latest_year": latest_year, "latest_extent": series[latest_year],
        "latest_band": severity_band(series[latest_year]),
        "worst_year": worst_year, "worst_extent": series[worst_year],
        "severe_years": severe_years,
        "years_since_last_severe": (latest_year - severe_years[-1]) if severe_years else None,
        "source": "Copernicus ERA5-Land raw-hourly, daily/seasonal minimum computed locally; "
                  "frozen-area fraction of the sub-region (season-min 2m temp ≤ %.0f°C)." % DAMAGE_THRESHOLD_C,
        "note": "Regional frost HAZARD severity (extent), not a calibrated euro — the frost→yield link "
                "does not clear the r²≥0.40 publish gate at any resolution (see analyze_coffee_frost_extent.py).",
    }


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    for region_key, cfg in REGIONS.items():
        rec = build(region_key, cfg)
        path = os.path.join(OUT_DIR, f"{region_key}.json")
        with open(path, "w") as f:
            json.dump(rec, f, indent=2)
        print(f"{region_key}: {rec['n_years']} yrs {rec['years_covered']}, latest {rec['latest_year']}="
              f"{rec['latest_extent']:.0%} ({rec['latest_band']}), worst {rec['worst_year']}="
              f"{rec['worst_extent']:.0%}, severe yrs {rec['severe_years']} → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
