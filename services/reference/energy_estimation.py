"""Estimates for a company's energy facts (SFDR PAI 5 and 6) when neither the company nor a data vendor reports them.

  energy consumption intensity  the EU-27 average for its activity (data/reference/nace_energy_intensity.csv — Eurostat
                                energy accounts ÷ turnover, finest NACE level published, else its section)
  non-renewable consumption     100 − its country's renewable share of primary energy
  non-renewable production      100 − its country's renewable share of electricity (energy producers, NACE D)
                                (data/reference/country_renewable_shares.csv — Our World in Data)

Each estimate says what it is and where it came from; the reader ranks it below a reported or vendor figure, and the
share of a fund's value resting on estimates is disclosed with every indicator. Never used when a real figure exists.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Optional

_REF = Path(__file__).resolve().parents[2] / "data" / "reference"
# NACE Rev. 2 division → section
_SECTION = [("A", 1, 3), ("B", 5, 9), ("C", 10, 33), ("D", 35, 35), ("E", 36, 39), ("F", 41, 43), ("G", 45, 47),
            ("H", 49, 53), ("I", 55, 56), ("J", 58, 63), ("K", 64, 66), ("L", 68, 68), ("M", 69, 75), ("N", 77, 82),
            ("O", 84, 84), ("P", 85, 85), ("Q", 86, 88), ("R", 90, 93), ("S", 94, 96), ("T", 97, 98), ("U", 99, 99)]


def division(nace_code: Optional[str]) -> Optional[int]:
    s = (nace_code or "").strip().lstrip("ABCDEFGHIJKLMNOPQRSTU").strip()
    try:
        return int(s.replace(".", "")[:2])
    except ValueError:
        return None


def section(nace_code: Optional[str]) -> Optional[str]:
    d = division(nace_code)
    if d is None:
        return None
    return next((sec for sec, lo, hi in _SECTION if lo <= d <= hi), None)


@lru_cache(maxsize=1)
def _intensities() -> tuple[dict, dict]:
    by_div, by_sec = {}, {}
    with (_REF / "nace_energy_intensity.csv").open() as f:
        for r in csv.DictReader(f):
            row = {"value": float(r["intensity_gwh_per_meur"]), "code": r["nace_code"], "year": int(r["year"])}
            if r["nace_code"] == r["section"]:
                by_sec[r["section"]] = row
            else:
                for d in r["divisions"].split(";"):
                    by_div[d] = row
    return by_div, by_sec


@lru_cache(maxsize=1)
def _country() -> dict:
    with (_REF / "country_renewable_shares.csv").open() as f:
        return {r["country_iso2"]: r for r in csv.DictReader(f)}


def intensity(nace_code: Optional[str]) -> Optional[dict]:
    """{value (GWh/€M revenue), basis} — the EU-27 average for the company's activity, or None if no NACE code."""
    sec, d = section(nace_code), division(nace_code)
    if sec is None:
        return None
    by_div, by_sec = _intensities()
    row = by_div.get(f"{sec}{d:02d}") or by_sec.get(sec)
    if not row:
        return None
    return {**row, "basis": f"EU-27 average for NACE {row['code']} ({row['year']}, Eurostat energy accounts ÷ turnover)"}


def non_renewable_consumption(country: Optional[str]) -> Optional[dict]:
    r = _country().get((country or "").strip().upper())
    if not r or not r["renewable_share_energy_pct"]:
        return None
    return {"value": round(100 - float(r["renewable_share_energy_pct"]), 3),
            "basis": f"{r['country_iso2']} renewable share of primary energy {r['energy_year']} (OWID)"}


def non_renewable_production(country: Optional[str]) -> Optional[dict]:
    r = _country().get((country or "").strip().upper())
    if not r or not r["renewable_share_elec_pct"]:
        return None
    return {"value": round(100 - float(r["renewable_share_elec_pct"]), 3),
            "basis": f"{r['country_iso2']} renewable share of electricity {r['elec_year']} (OWID)"}
