"""Build the ISO 4217 currency reference from the maintenance agency's own list (SIX, "List One — current currency &
funds"). Writes data/reference/iso4217.csv: code, name, numeric code, minor units (decimals — blank for precious
metals and special codes), whether it is a fund / non-circulating code (XAU, XDR, …), and its symbols from the Unicode
CLDR — the English locale's symbol (e.g. $), international English's (en-001, e.g. US$) and the narrow one (e.g. $),
pinned to the CLDR version the country reference uses. The ONE place the platform learns which three-letter codes are currencies, how many decimals
they have, and which written symbols identify one currency and which several share (services/reference/iso4217.py). Re-run when SIX publishes an amendment:
    python -m scripts.build_iso4217
"""
from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

URL = "https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/lists/list-one.xml"
OUT = Path(__file__).resolve().parent.parent / "data" / "reference" / "iso4217.csv"


def _cldr_symbols() -> dict[str, tuple[str, str, str]]:
    """code → (English symbol, international-English symbol, narrow symbol, English names 'euro;euros;Euro')."""
    from services.reference.countries import _BASE

    def load(loc: str) -> dict:
        return requests.get(f"{_BASE}/cldr-numbers-full/main/{loc}/currencies.json", timeout=60).json()["main"][loc]["numbers"]["currencies"]
    en, intl = load("en"), load("en-001")
    return {k: (v.get("symbol", ""), (intl.get(k) or {}).get("symbol", ""), v.get("symbol-alt-narrow", ""),
                ";".join(sorted({v[n] for n in ("displayName", "displayName-count-one", "displayName-count-other") if v.get(n)})))
            for k, v in en.items()}


def build() -> int:
    symbols = _cldr_symbols()
    root = ET.fromstring(requests.get(URL, timeout=60).content)
    published = root.get("Pblshd")
    seen: dict[str, list] = {}
    for e in root.iter("CcyNtry"):
        code = (e.findtext("Ccy") or "").strip()
        if len(code) != 3:
            continue
        mnr = (e.findtext("CcyMnrUnts") or "").strip()
        fund = (e.find("CcyNm") is not None and e.find("CcyNm").get("IsFund") == "true") or code.startswith("X")
        sym, intl, narrow, names = symbols.get(code, ("", "", "", ""))
        seen.setdefault(code, [code, (e.findtext("CcyNm") or "").strip(), (e.findtext("CcyNbr") or "").strip(),
                               mnr if mnr.isdigit() else "", "yes" if fund else "", sym, intl, narrow, names, published])
    if not {"EUR", "USD", "GBP"} <= set(seen):
        raise SystemExit("unexpected ISO 4217 list — refusing to write")
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["code", "name", "numeric", "minor_units", "non_circulating", "symbol", "symbol_intl", "narrow_symbol", "names", "published"])
        w.writerows(sorted(seen.values()))
    print(f"wrote {len(seen)} ISO 4217 codes (published {published}) → {OUT}")
    return len(seen)


if __name__ == "__main__":
    build()
