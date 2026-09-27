"""How a filing writes money: in the currency its frozen snapshot says it presents in (multi-currency phase 3).

A snapshot records its currency in payload["_fx"]["presentation_currency"]; one frozen before that existed was in
EUR. Amount keys keep their `_eur` names (the engine's contract) — every renderer reads the currency from here, so a
USD filing never shows "€".
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

SYMBOL = {"EUR": "€", "USD": "US$", "GBP": "£", "JPY": "¥", "CHF": "CHF ", "SEK": "SEK ", "NOK": "NOK ", "DKK": "DKK ",
          "PLN": "PLN ", "CZK": "CZK ", "HUF": "HUF ", "RON": "RON ", "CAD": "C$", "AUD": "A$", "BRL": "R$", "INR": "₹"}

# the currency of the filing being rendered — set by the renderer entry point (filing_annex.build_annex) for its
# nested cell formatters, reset when it returns
current: ContextVar[str] = ContextVar("filing_currency", default="EUR")


def presentation_of(payload: Optional[dict]) -> str:
    return (((payload or {}).get("_fx") or {}).get("presentation_currency") or "EUR").strip().upper()


def symbol(ccy: str) -> str:
    return SYMBOL.get(ccy, f"{ccy} ")


def money(v, ccy: Optional[str] = None, compact: bool = True) -> str:
    """'€12.3m' / 'US$1.20bn' / 'CHF 950k' — or the full figure with thousands separators when compact=False."""
    if not isinstance(v, (int, float)):
        return "—"
    s, n = symbol(ccy or current.get()), float(v)
    if not compact:
        return f"{s}{n:,.0f}"
    if n == 0:
        return f"{s}0"
    if abs(n) >= 1e9:
        return f"{s}{n / 1e9:.2f}bn"
    if abs(n) >= 1e6:
        return f"{s}{n / 1e6:.1f}m"
    if abs(n) >= 1e3:
        return f"{s}{round(n / 1e3):,}k"
    return f"{s}{round(n):,}"
