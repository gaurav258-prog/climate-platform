"""Countries from the Unicode CLDR: every accepted way of writing a country → its ISO 3166 alpha-2 code.

Source: Unicode CLDR (cldr-json), pinned to CLDR_VERSION — the reference behind operating-system and browser country
names, published under the Unicode licence. We take:
  * codes: alpha-2, alpha-3, numeric (supplemental/codeMappings)
  * names in the EU's 24 official languages plus Norwegian and Turkish, including CLDR's short and variant forms
    ('UK', 'Czech Republic', 'Turkey')
  * each country's current legal-tender currency and since when (supplemental/currencyData)
plus a short, labelled list of common business forms CLDR does not carry ('USA', 'Holland').

A written form that normalises to two different countries is dropped: it is reported as not recognised, never
guessed. (A bare 'Congo' is kept: in CLDR, as in ISO 3166, it is the Republic of the Congo, CG.)
"""
from __future__ import annotations

import json
import urllib.request
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.ingest.fields import norm_token
from services.reference.iso_country import ISO_ALPHA2

CLDR_VERSION = "48.0.0"   # latest stable; bump on each CLDR release (e.g. 48 carries Bulgaria's euro from 2026-01-01)
_BASE = f"https://raw.githubusercontent.com/unicode-org/cldr-json/{CLDR_VERSION}/cldr-json"
LOCALES = ("en", "bg", "cs", "da", "de", "el", "es", "et", "fi", "fr", "ga", "hr", "hu", "it", "lt", "lv", "mt",
           "nl", "pl", "pt", "ro", "sk", "sl", "sv", "nb", "tr")
# Common business forms not in CLDR. Each is an unambiguous reference to ONE country.
CURATED = {"USA": "US", "U.S.A.": "US", "U.S.": "US", "United States of America": "US", "UAE": "AE",
           "Holland": "NL", "The Netherlands": "NL", "Great Britain": "GB", "England": "GB", "Scotland": "GB",
           "Wales": "GB", "Northern Ireland": "GB", "Republic of Ireland": "IE", "South Korea": "KR",
           "Russia": "RU", "Czech Rep.": "CZ", "Slovak Republic": "SK"}


def _get(path: str) -> dict:
    req = urllib.request.Request(f"{_BASE}/{path}", headers={"User-Agent": "Tellumen/1.0 (CLDR reference)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def _current_currency(entries: list[dict]) -> tuple[Optional[str], Optional[str]]:
    """CLDR lists every currency a region has had; the current one has no end date and is legal tender."""
    best = (None, None)
    for e in entries:
        (ccy, meta), = e.items()
        if "_to" in meta or meta.get("_tender") == "false":
            continue
        if best[1] is None or (meta.get("_from") or "") > best[1]:
            best = (ccy, meta.get("_from"))
    return best


def build(names_by_locale: dict[str, dict], code_mappings: dict, currency_data: dict) -> tuple[list[dict], list[dict]]:
    """Pure: CLDR JSON → (country rows, name rows). Ambiguous normalised names are dropped."""
    en = names_by_locale["en"]
    countries = []
    for iso2 in sorted(k for k in en if len(k) == 2 and k.isalpha() and k in ISO_ALPHA2):
        m = code_mappings.get(iso2, {})
        ccy, since = _current_currency(currency_data.get(iso2, []))
        countries.append({"iso2": iso2, "iso3": m.get("_alpha3"), "numeric_code": m.get("_numeric"), "name_en": en[iso2],
                          "currency": ccy, "currency_from": since, "source_version": f"CLDR {CLDR_VERSION}"})
    known = {c["iso2"] for c in countries}

    cands: dict[str, set] = {}
    first: dict[str, dict] = {}

    def add(written: str, iso2: str, locale: Optional[str], kind: str) -> None:
        n = norm_token(written)
        if not n or iso2 not in known:
            return
        cands.setdefault(n, set()).add(iso2)
        first.setdefault(n, {"name_norm": n, "iso2": iso2, "name": written, "locale": locale, "kind": kind})

    for c in countries:
        for code in (c["iso2"], c["iso3"], c["numeric_code"]):
            if code:
                add(code, c["iso2"], None, "code")
    for loc, terr in names_by_locale.items():
        for key, name in terr.items():
            base, _, alt = key.partition("-alt-")
            add(name, base, loc, "variant" if alt else "name")
    for written, iso2 in CURATED.items():
        add(written, iso2, None, "curated")
    names = [first[n] for n, isos in cands.items() if len(isos) == 1]
    return countries, names


def refresh(session: Session) -> dict:
    names = {loc: _get(f"cldr-localenames-full/main/{loc}/territories.json")["main"][loc]["localeDisplayNames"]["territories"]
             for loc in LOCALES}
    codes = _get("cldr-core/supplemental/codeMappings.json")["supplemental"]["codeMappings"]
    currencies = _get("cldr-core/supplemental/currencyData.json")["supplemental"]["currencyData"]["region"]
    countries, rows = build(names, codes, currencies)
    session.execute(text("""
        INSERT INTO ref_countries (iso2, iso3, numeric_code, name_en, currency, currency_from, source_version, loaded_at)
        VALUES (:iso2, :iso3, :numeric_code, :name_en, :currency, CAST(:currency_from AS date), :source_version, now())
        ON CONFLICT (iso2) DO UPDATE SET iso3 = EXCLUDED.iso3, numeric_code = EXCLUDED.numeric_code,
               name_en = EXCLUDED.name_en, currency = EXCLUDED.currency, currency_from = EXCLUDED.currency_from,
               source_version = EXCLUDED.source_version, loaded_at = now()
    """), countries)
    session.execute(text("DELETE FROM ref_country_names"))
    session.execute(text("""INSERT INTO ref_country_names (name_norm, iso2, name, locale, kind)
                            VALUES (:name_norm, :iso2, :name, :locale, :kind)"""), rows)
    session.commit()
    return {"countries": len(countries), "names": len(rows), "version": CLDR_VERSION, "loaded_on": date.today().isoformat()}


def lookup(session: Session) -> dict[str, str]:
    """normalised written form → alpha-2 (empty until the reference is loaded)."""
    return {r[0]: r[1] for r in session.execute(text("SELECT name_norm, iso2 FROM ref_country_names")).all()}
