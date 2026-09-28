"""ISO 4217 currencies — the ONE place the platform learns which three-letter codes are currencies, how many decimals
each has, and which written symbols identify a currency (data/reference/iso4217.csv, built from the SIX list and the
Unicode CLDR by scripts/build_iso4217.py).

A symbol identifies a currency only when no other current currency uses it (as its symbol or narrow symbol): '€',
'CA$', 'A$', 'US$'. '$', '£', '¥', 'kr' are each shared by several — they are AMBIGUOUS and resolve only through a
currency the sender declares; never guessed.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Optional

_FILE = Path(__file__).resolve().parents[2] / "data" / "reference" / "iso4217.csv"


@lru_cache(maxsize=1)
def _rows() -> dict[str, dict]:
    with _FILE.open() as f:
        return {r["code"]: r for r in csv.DictReader(f)}


def codes(circulating_only: bool = True) -> frozenset[str]:
    return frozenset(c for c, r in _rows().items() if not (circulating_only and r["non_circulating"]))


def minor_units(code: str) -> Optional[int]:
    r = _rows().get((code or "").upper())
    return int(r["minor_units"]) if r and r["minor_units"] else None


def name(code: str) -> Optional[str]:
    r = _rows().get((code or "").upper())
    return r["name"] if r else None


@lru_cache(maxsize=1)
def _symbols() -> tuple[dict[str, str], frozenset[str]]:
    users: dict[str, set] = {}
    for c, r in _rows().items():
        if r["non_circulating"]:
            continue
        for s in {r["symbol"], r["symbol_intl"], r["narrow_symbol"]}:
            if s and s != c:                      # a symbol that is just the code adds nothing
                users.setdefault(s, set()).add(c)
    unique = {s: next(iter(cs)) for s, cs in users.items() if len(cs) == 1}
    return unique, frozenset(s for s, cs in users.items() if len(cs) > 1)


def symbol_currency(symbol: str) -> Optional[str]:
    """The one currency a symbol identifies, else None (unknown, or shared by several)."""
    return _symbols()[0].get(symbol)


@lru_cache(maxsize=1)
def names() -> dict[str, str]:
    """A currency's English names (CLDR) → its code, lower-case, only where the name belongs to one currency."""
    users: dict[str, set] = {}
    for c, r in _rows().items():
        if not r["non_circulating"]:
            for n in (r.get("names") or "").split(";"):
                if n:
                    users.setdefault(n.lower(), set()).add(c)
    return {n: next(iter(cs)) for n, cs in users.items() if len(cs) == 1}


def unique_symbols() -> dict[str, str]:
    return dict(_symbols()[0])


def ambiguous_symbols() -> frozenset[str]:
    return _symbols()[1]
