"""Units of reported figures read from a customer's past filings (XBRL, iXBRL, Excel, PDF) — multi-currency phase 4.

A figure is only comparable with another in the SAME unit. Every reader normalises to one vocabulary:

    money      → its ISO 4217 code ('EUR', 'USD', 'GBP', …)   from €/$/£/¥ signs, ISO codes, or iso4217: measures
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

CURRENCIES = frozenset("EUR USD GBP CHF JPY SEK NOK DKK PLN CZK HUF RON BGN ISK CAD AUD NZD CNY HKD SGD INR BRL ZAR MXN "
                       "KRW TRY ILS AED SAR".split())
_SIGNS = (("US$", "USD"), ("€", "EUR"), ("£", "GBP"), ("¥", "JPY"), ("$", "USD"))
_WORD_CCY = {"euro": "EUR", "euros": "EUR", "dollar": "USD", "dollars": "USD", "pound": "GBP", "pounds": "GBP",
             "sterling": "GBP", "franc": "CHF", "francs": "CHF"}
_SCALE = ((r"\b(?:bn|billions?|mrd\.?|milliarden?)\b", 1e9),
          (r"(?<=\d)\s?bn\b|(?<=\d)\s?b\b", 1e9),
          (r"\b(?:mn|mio\.?|millions?|mln)\b|(?<=\d)\s?m\b|\bm(?=\s*[€$£)])|(?<=[€$£])\s?m\b|\b(?:eur|usd|gbp|chf)\s?m\b", 1e6),
          (r"\b(?:thousands?|tsd\.?|tausend)\b|'000|(?<=\d)\s?k\b|\b(?:eur|usd|gbp|chf)\s?k\b", 1e3))
_PHYSICAL = ((r"t\s?co2\s?-?e(q)?|tonnes? co2|tco₂e", "tCO2e"), (r"\bgwh\b", "GWh"), (r"\bmwh\b", "MWh"),
             (r"\bhectares?\b|\bha\b", "ha"))


def is_currency(unit: Optional[str]) -> bool:
    return bool(unit) and unit in CURRENCIES


def from_text(s: Optional[str]) -> tuple[Optional[str], float]:
    """(unit, scale) stated in a value or a label: '€12.3m' → ('EUR', 1e6); 'Total assets (USD thousands)' →
    ('USD', 1e3); '12.5%' → ('%', 1); 'Scope 1 (tCO2e)' → ('tCO2e', 1); nothing stated → (None, 1)."""
    if not s:
        return None, 1.0
    raw = str(s)
    low = raw.lower()
    unit = None
    if "%" in raw:
        unit = "%"
    if unit is None:
        for sign, code in _SIGNS:
            if sign in raw:
                unit = code
                break
    if unit is None:
        # an ISO code only in capitals ('USD 5m', 'in EUR'): lower-case 'try' or 'eur' inside a word is not a currency
        m = re.search(r"(?<![A-Za-z])(" + "|".join(sorted(CURRENCIES)) + r")(?![A-Za-z])", raw)
        if m:
            unit = m.group(1)
    if unit is None:
        for w, code in _WORD_CCY.items():
            if re.search(rf"\b{w}\b", low):
                unit = code
                break
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
    if s.lower() in ("pure", "ratio"):
        return "pure"
    u, _ = from_text(s)
    return u or s
