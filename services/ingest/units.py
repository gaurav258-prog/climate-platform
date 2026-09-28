"""Units of reported figures read from a customer's past filings (XBRL, iXBRL, Excel, PDF) — multi-currency phase 4.

A figure is only comparable with another in the SAME unit. Every reader normalises to one vocabulary:

    money      → its ISO 4217 code ('EUR', 'USD', …) from an ISO code, an iso4217: measure, a symbol only one currency
                 uses ('€', 'US$', 'CA$') or a currency's own name ('euros') — all from services.reference.iso4217
               → the bare SYMBOL ('$', '£', '¥', 'kr') when several currencies share it: ambiguous, resolved only by the
                 currency the sender declares for the file (resolve_declared), never guessed
    percentage → '%'
    ratio      → 'pure'                                       (xbrli:pure)
    emissions  → 'tCO2e'; energy → 'MWh' / 'GWh'; area → 'ha'
    otherwise  → the measure's own name, or None when nothing says (never guessed)

and returns a SCALE (×1e3 / ×1e6 / ×1e9) from magnitude words ('€12.3m', 'EUR thousands', 'Mio. €', 'bn'), which the
reader applies to the value — a table 'in € millions' holds millions, not units.
"""
from __future__ import annotations

import re
from typing import Optional

from services.reference import iso4217

CURRENCIES = iso4217.codes()
# magnitude words, in the languages filings are written in (parsing grammar, not reference data)
_CCY = "|".join(sorted(c.lower() for c in CURRENCIES))
_SCALE = ((r"\b(?:bn|billions?|mrd\.?|milliarden?|mds?)\b|(?<=\d)\s?bn?\b", 1e9),
          (r"\b(?:mn|mio\.?|millions?|mln|m€)\b|(?<=\d)\s?m\b|\bm(?=\s*[^\w\s])|(?<=[^\w\s])\s?m\b"
           rf"|\b(?:{_CCY})\s?m\b", 1e6),
          (rf"\b(?:thousands?|tsd\.?|tausend|milliers?)\b|'000|(?<=\d)\s?k\b|\b(?:{_CCY})\s?k\b", 1e3))
_PHYSICAL = ((r"t\s?co2\s?-?e(q)?|tonnes? co2|tco₂e", "tCO2e"), (r"\bgwh\b", "GWh"), (r"\bmwh\b", "MWh"),
             (r"\bhectares?\b|\bha\b", "ha"))


def is_currency(unit: Optional[str]) -> bool:
    return bool(unit) and unit in CURRENCIES


def is_ambiguous_money(unit: Optional[str]) -> bool:
    """A currency symbol several currencies share ('$', '£', '¥') — money, but which currency the file must say."""
    return bool(unit) and unit in iso4217.ambiguous_symbols()


def resolve_declared(unit: Optional[str], declared: Optional[str]) -> Optional[str]:
    """A shared symbol takes the currency the sender declared for the file; everything else stays as read."""
    return declared if (declared and is_ambiguous_money(unit)) else unit


def _money(raw: str, low: str) -> Optional[str]:
    unique = iso4217.unique_symbols()
    for sym in sorted(unique, key=len, reverse=True):              # longest first: US$ before $
        if not sym.isalpha() and sym in raw:
            return unique[sym]
    # an ISO code only in capitals ('USD 5m', 'in EUR'): lower-case 'try' or 'eur' inside a word is not a currency
    m = re.search(r"(?<![A-Za-z])(" + "|".join(sorted(CURRENCIES)) + r")(?![A-Za-z])", raw)
    if m:
        return m.group(1)
    for sym in sorted(unique, key=len, reverse=True):              # alphabetic symbols ('Fr.') as whole words
        if sym.isalpha() and re.search(rf"(?<![A-Za-z]){re.escape(sym)}(?![A-Za-z])", raw):
            return unique[sym]
    names = iso4217.names()
    for n in sorted(names, key=len, reverse=True):                 # a currency's own name ('euros', 'us dollars')
        if re.search(rf"(?<![a-z]){re.escape(n)}(?![a-z])", low):
            return names[n]
    for sym in sorted(iso4217.ambiguous_symbols(), key=len, reverse=True):
        hit = (re.search(rf"(?<![A-Za-z]){re.escape(sym)}(?![A-Za-z])", raw) if sym.isalpha() else sym in raw)
        if hit:
            return sym                                              # shared symbol: kept as written, never guessed
    return None


def from_text(s: Optional[str]) -> tuple[Optional[str], float]:
    """(unit, scale) stated in a value or a label: '€12.3m' → ('EUR', 1e6); 'Total assets (USD thousands)' →
    ('USD', 1e3); '$450k' → ('$', 1e3) — which dollar, the file must say; '12.5%' → ('%', 1); nothing → (None, 1)."""
    if not s:
        return None, 1.0
    raw = str(s)
    low = raw.lower()
    unit = "%" if "%" in raw else _money(raw, low)
    if unit is None:
        for pat, u in _PHYSICAL:
            if re.search(pat, low):
                unit = u
                break
    scale = 1.0
    if unit != "%":
        for pat, k in _SCALE:
            if re.search(pat, low):
                scale = k
                break
    return unit, scale


def from_measure(measure: Optional[str]) -> Optional[str]:
    """An XBRL unit measure → our unit: 'iso4217:USD' → 'USD', 'xbrli:pure' → 'pure', 'esrs:tCO2e' → 'tCO2e'."""
    if not measure:
        return None
    m = measure.strip()
    local = m.rsplit(":", 1)[-1]
    if m.lower().startswith("iso4217:") or local.upper() in CURRENCIES:
        return local.upper()
    if local.lower() == "pure":
        return "pure"
    u, _ = from_text(local)
    return u or local


def normalise(unit: Optional[str]) -> Optional[str]:
    """A unit a person typed (confirm step) → our vocabulary; unknown text is kept as given, blank → None."""
    if unit is None or not str(unit).strip():
        return None
    s = str(unit).strip()
    if s.upper() in CURRENCIES:
        return s.upper()
    if iso4217.symbol_currency(s):
        return iso4217.symbol_currency(s)
    if s.lower() in ("pure", "ratio"):
        return "pure"
    u, _ = from_text(s)
    return u or s
