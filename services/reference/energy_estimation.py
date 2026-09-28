"""Estimates for a company's energy facts (SFDR PAI 5 and 6) when neither the company nor a data vendor reports them.

  energy consumption intensity  its OWN COUNTRY's figure for its activity where that country reports it to Eurostat
                                (nace_energy_intensity_by_country.csv), else the European figure for its activity
                                (nace_energy_intensity.csv — the countries reporting every part, summed), finest NACE
                                level published, else its section. The activity is resolved by services.reference.nace.
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

from services.reference import nace

_REF = Path(__file__).resolve().parents[2] / "data" / "reference"


def section(nace_code: Optional[str]) -> Optional[str]:
    return nace.section(nace_code)


@lru_cache(maxsize=1)
def _intensities() -> tuple[dict, dict]:
    """(division → European figure, section → European figure). A figure the table marks thin (too few reporting
    countries) is not used for a division — the section's figure is the better estimate then."""
    by_div, by_sec = {}, {}
    with (_REF / "nace_energy_intensity.csv").open() as f:
        for r in csv.DictReader(f):
            row = {"value": float(r["intensity_gwh_per_meur"]), "code": r["nace_code"], "year": int(r["year"]),
                   "n": int(r["n_countries"])}
            if r["nace_code"] == r["section"]:
                by_sec[r["section"]] = row
            elif not r["thin"]:
                for d in r["divisions"].split(";"):
                    by_div[d] = row
    return by_div, by_sec


@lru_cache(maxsize=1)
def _by_country() -> dict:
    out: dict = {}
    with (_REF / "nace_energy_intensity_by_country.csv").open() as f:
        for r in csv.DictReader(f):
            row = {"value": float(r["intensity_gwh_per_meur"]), "code": r["nace_code"], "year": int(r["year"])}
            keys = [r["section"]] if r["nace_code"] == r["section"] else r["divisions"].split(";")
            for k in keys:
                out[(r["country_iso2"], k)] = row
    return out


@lru_cache(maxsize=1)
def _country() -> dict:
    with (_REF / "country_renewable_shares.csv").open() as f:
        return {r["country_iso2"]: r for r in csv.DictReader(f)}


def intensity(nace_code: Optional[str], country: Optional[str] = None) -> Optional[dict]:
    """{value (GWh/€M revenue), basis} — the company's country figure for its activity where that country reports it to
    Eurostat, else the European figure; None if the code isn't a NACE activity the table covers."""
    sec, div = nace.section(nace_code), nace.division(nace_code)
    if sec is None:
        return None
    c = (country or "").strip().upper()
    own = _by_country()
    row = (own.get((c, div)) if div else None) or own.get((c, sec))
    if row:
        return {**row, "basis": f"{c} national figure for NACE {row['code']} ({row['year']}, Eurostat energy accounts ÷ turnover)"}
    by_div, by_sec = _intensities()
    row = (by_div.get(div) if div else None) or by_sec.get(sec)
    if not row:
        return None
    where = f" — no national figure for {c}" if c else ""
    return {**row, "basis": f"average of {row['n']} European countries for NACE {row['code']} ({row['year']}, "
                            f"Eurostat energy accounts ÷ turnover){where}"}


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
