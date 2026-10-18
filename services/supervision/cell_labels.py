"""Customer names for a template cell's two codes (UI standard, product owner 2026-10-16): a screen never shows 'ES · D'.

  geography — a country, written as ISO 3166 or as the EU writes it ('EL', 'UK'), or a grouping ('EU'): its English
              name from the country reference (services.reference.countries)
  sector    — a NACE section letter: its official title (services.reference.nace); a bucket the template defines
              ('OLIVE OIL', 'OFFICE'): the same words in sentence case
A code no reference holds is named as unrecognised, never guessed; an empty or '?' code is named as not stated.
"""
from __future__ import annotations

from typing import Optional

from services.reference import nace
from services.reference.countries import english_name

_UNSTATED = {"", "?"}


def geography_label(code: Optional[str]) -> str:
    c = (code or "").strip().upper()
    if c in _UNSTATED:
        return "Geography not stated"
    return english_name(c) or f"Unrecognised code {c}"


def sector_label(code: Optional[str]) -> str:
    c = (code or "").strip()
    if c in _UNSTATED:
        return "Sector not stated"
    sections = nace.section_labels()
    if c.upper() in sections:
        return sections[c.upper()]
    return c[:1].upper() + c[1:].lower()


def named(cell: dict) -> dict:
    """The cell with its geography_label and sector_label beside the codes."""
    return {**cell, "geography_label": geography_label(cell.get("geography")), "sector_label": sector_label(cell.get("sector"))}
