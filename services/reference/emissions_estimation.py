"""Estimate issuer emissions from sector + revenue, when nothing is disclosed.

The honest last resort. If a customer can't give us an issuer's emissions and no
public disclosure is on file, but we DO know the issuer's industry (NACE) and
revenue, we estimate scope 1+2 as:

    estimated_scope1_2  =  sector_average_intensity(NACE) × revenue(€M)

This is the standard "economic activity / sector-average intensity" estimation
(the fallback tier in PCAF and CDP methodologies). It is never presented as a
disclosed figure: every estimate is written source='estimated' with an explicit
estimation_method, and the SFDR statement reports the estimated-vs-reported split
(which the RTS itself requires).

Honesty & scope:
  * Needs BOTH a NACE code and revenue. Missing either → returns None (a real
    gap, surfaced, not a fabricated zero).
  * Scope 3 is NOT estimated here — value-chain estimation from sector intensity
    is far weaker and would overstate confidence. Scope 3 stays a disclosed gap.
  * The intensity coefficients below are order-of-magnitude sector averages
    (scope 1+2, tCO2e per €M revenue). They are illustrative and MUST be replaced
    with a cited open dataset (EXIOBASE environmentally-extended I-O tables are
    the intended source) before a filing relies on them — flagged, not hidden.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MODEL_VERSION = "emissions-est-v1-sector-intensity"

# Coefficients live in a provenanced data file (data/reference/nace_emission_intensity.csv)
# so they are auditable data, not magic numbers — regenerate with
# scripts/build_nace_intensities.py (documents the EXIOBASE pipeline). The embedded
# dict below is the offline fallback if the file is absent.
_INTENSITY_CSV = Path(__file__).resolve().parent.parent.parent / "data" / "reference" / "nace_emission_intensity.csv"

# NACE division (first 2 digits) → sector-average scope 1+2 intensity,
# tCO2e per €M revenue. Illustrative averages pending an EXIOBASE-sourced table.
NACE_INTENSITY_TCO2E_PER_MEUR: dict[str, float] = {
    "01": 600, "02": 300, "03": 250,                       # agriculture, forestry, fishing
    "05": 2000, "06": 800, "07": 500, "08": 500, "09": 450,  # mining & extraction
    "10": 300, "11": 250, "12": 200,                        # food, beverages, tobacco
    "13": 220, "14": 180, "15": 180,                        # textiles, apparel, leather
    "16": 400, "17": 500, "18": 150,                        # wood, paper, printing
    "19": 1500, "20": 700, "21": 120, "22": 400, "23": 900,  # coke/refining, chemicals, pharma, plastics, cement/glass
    "24": 1800, "25": 200, "26": 80, "27": 150, "28": 150,   # basic metals, fabricated, electronics, electrical, machinery
    "29": 150, "30": 200,                                   # vehicles, other transport equipment
    "31": 150, "32": 120, "33": 120,                        # furniture, other mfg, repair
    "35": 2500, "36": 300, "37": 350, "38": 500, "39": 400,  # electricity/gas, water, sewerage, waste
    "41": 150, "42": 250, "43": 120,                        # construction
    "45": 90, "46": 90, "47": 80,                           # trade
    "49": 500, "50": 700, "51": 1000, "52": 300, "53": 250,  # transport (land/water/air/warehousing/postal)
    "55": 150, "56": 120,                                   # accommodation, food service
    "58": 40, "59": 40, "60": 60, "61": 60, "62": 30, "63": 40,  # info & communication, software
    "64": 20, "65": 20, "66": 20,                           # financial & insurance (operational only)
    "68": 150,                                              # real estate
    "69": 40, "70": 40, "71": 60, "72": 60, "73": 40, "74": 40, "75": 40,  # professional/scientific
    "77": 90, "78": 40, "79": 60, "80": 40, "81": 90, "82": 40,  # admin & support
    "84": 80, "85": 60, "86": 80, "87": 80, "88": 60,       # public admin, education, health, social
    "90": 40, "91": 40, "92": 60, "93": 90,                 # arts, entertainment, recreation
    "94": 40, "95": 60, "96": 90,                           # other services
}

DEFAULT_INTENSITY = 150.0  # unknown division → a mid economy-wide average, flagged


def _load_intensities() -> dict[str, float]:
    """Load NACE intensities from the provenanced CSV; fall back to the embedded
    table if the file is missing (offline / tests)."""
    try:
        with open(_INTENSITY_CSV, newline="", encoding="utf-8") as fh:
            table = {r["nace_division"].strip(): float(r["intensity_tco2e_per_meur"])
                     for r in csv.DictReader(fh) if r.get("nace_division")}
        if table:
            return table
    except (OSError, KeyError, ValueError) as exc:
        logger.info("NACE intensity CSV unavailable (%s); using embedded fallback", exc)
    return dict(NACE_INTENSITY_TCO2E_PER_MEUR)


# Effective table used by estimate_emissions (data file, else embedded fallback).
_INTENSITIES = _load_intensities()


def estimate_emissions(nace_code: Optional[str], revenue_eur: Optional[float]) -> Optional[dict]:
    """Estimate scope 1+2 tCO2e from sector intensity × revenue.

    Returns {scope1_2_tco2e, intensity_tco2e_per_meur, method, revenue_eur} or
    None if either input is missing (an honest gap). Scope 3 is deliberately not
    estimated.
    """
    if not nace_code or revenue_eur is None or revenue_eur <= 0:
        return None
    division = str(nace_code).strip()[:2]
    intensity = _INTENSITIES.get(division, DEFAULT_INTENSITY)
    known = division in _INTENSITIES
    revenue_meur = revenue_eur / 1e6
    return {
        "scope1_2_tco2e": round(intensity * revenue_meur),
        "intensity_tco2e_per_meur": intensity,
        "method": f"nace_intensity_x_revenue:{MODEL_VERSION}"
                  + ("" if known else ":default_division"),
        "revenue_eur": revenue_eur,
    }
