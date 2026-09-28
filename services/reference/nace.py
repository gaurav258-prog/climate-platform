"""NACE Rev. 2 — the ONE place the platform maps an activity code to its division, section and official title.

Read from data/reference/nace_rev2.csv (built from Eurostat's official code list by scripts/build_nace_reference.py).
Companies write codes in several forms — '24.10', '2410', 'C24.10', 'C2410', '24', 'C' — all resolve here. A code the
classification doesn't contain resolves to None; callers show it as unclassified, never guess a sector.
"""
from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

_FILE = Path(__file__).resolve().parents[2] / "data" / "reference" / "nace_rev2.csv"


@lru_cache(maxsize=1)
def _table() -> dict:
    by_code, by_dotted, sections = {}, {}, {}
    with _FILE.open() as f:
        for r in csv.DictReader(f):
            by_code[r["code"]] = r
            if r["dotted"]:
                by_dotted[r["dotted"]] = r
            if r["level"] == "section":
                sections[r["section"]] = r["label"]
    return {"by_code": by_code, "by_dotted": by_dotted, "sections": sections}


def lookup(nace_code: Optional[str]) -> Optional[dict]:
    """The classification entry for a code in any usual written form, else None."""
    s = re.sub(r"\s+", "", str(nace_code or "")).upper()
    if not s:
        return None
    t = _table()
    if s in t["by_code"]:
        return t["by_code"][s]
    m = re.fullmatch(r"([A-U])?(\d{2})(?:\.?(\d{1,2}))?", s)
    if not m:
        return None
    dotted = m.group(2) + (f".{m.group(3)}" if m.group(3) else "")
    hit = t["by_dotted"].get(dotted)
    if hit and m.group(1) and hit["section"] != m.group(1):
        return None                                  # 'B24' — a letter that contradicts the division
    return hit


def section(nace_code: Optional[str]) -> Optional[str]:
    hit = lookup(nace_code)
    return hit["section"] if hit else None


def division(nace_code: Optional[str]) -> Optional[str]:
    """'C24' for '24.10' — section letter + two digits, the form Eurostat statistics use."""
    hit = lookup(nace_code)
    if not hit or hit["level"] == "section":
        return None
    return hit["section"] + hit["dotted"][:2]


def section_labels() -> dict[str, str]:
    return dict(_table()["sections"])


def label(nace_code: Optional[str]) -> Optional[str]:
    hit = lookup(nace_code)
    return hit["label"] if hit else None


def divisions_in(code_range: str) -> list[str]:
    """Eurostat activity aggregates → the divisions they cover: 'C10-C12' → C10, C11, C12; 'C31_C32'; a section 'D' →
    every division in D. Only divisions the classification contains — Eurostat's own non-NACE codes ('L68A', imputed
    rents of owner-occupied dwellings) resolve to nothing."""
    t = _table()["by_code"]
    out: list[str] = []
    for chunk in code_range.split("_"):
        m = re.fullmatch(r"([A-U])(\d{2})-(?:[A-U])?(\d{2})", chunk)
        if m:
            out += [c for n in range(int(m.group(2)), int(m.group(3)) + 1) if (c := f"{m.group(1)}{n:02d}") in t]
        elif re.fullmatch(r"[A-U]", chunk):
            out += [c for c, r in t.items() if r["section"] == chunk and r["level"] == "division"]
        elif chunk in t:
            out.append(chunk)
    return out
