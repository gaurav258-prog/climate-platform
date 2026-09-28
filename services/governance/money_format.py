"""How a filing writes money: in the currency its frozen snapshot says it presents in (multi-currency phase 3).

A snapshot records its currency in payload["_fx"]["presentation_currency"]; one frozen before that existed was in
EUR. Symbols come from the ISO 4217 / CLDR reference (services/reference/iso4217.py), never a local table. Amount
keys keep their `_eur` names (the engine's contract) — every renderer reads the currency from here, so a USD filing
never shows "€".
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

# the currency of the filing being rendered — set by the renderer entry point (filing_annex.build_annex) for its
# nested cell formatters, reset when it returns
current: ContextVar[str] = ContextVar("filing_currency", default="EUR")


def presentation_of(payload: Optional[dict]) -> str:
    return (((payload or {}).get("_fx") or {}).get("presentation_currency") or "EUR").strip().upper()


def symbol(ccy: str) -> str:
    """The currency's written symbol from the ISO 4217 / CLDR reference ('€', 'US$', 'CA$'); a code-like symbol
    ('SEK', 'CHF') is followed by a space."""
    from services.reference.iso4217 import display_symbol
    s = display_symbol(ccy)
    return f"{s} " if s[-1:].isalpha() else s


def money(v, ccy: Optional[str] = None, compact: bool = True) -> str:
    """'€12.3m' / 'US$1.20bn' / 'CHF 950k' — or the full figure with thousands separators when compact=False."""
    if not isinstance(v, (int, float)):
        return "—"
    s, n = symbol(ccy or current.get()), float(v)
    sign, a = ("−" if n < 0 else ""), abs(n)     # the minus before the symbol: '−€4.1m', as the screens write it
    if not compact:
        return f"{sign}{s}{a:,.0f}"
    if a >= 1e9:
        return f"{sign}{s}{a / 1e9:.2f}bn"
    if a >= 1e6:
        return f"{sign}{s}{a / 1e6:.1f}m"
    if a >= 1e3:
        return f"{sign}{s}{round(a / 1e3):,}k"
    return f"{sign}{s}{round(a):,}"
