"""The region reference (E157): the sub-national units a regional fact may name, from the official lists only.

  ISO 3166-2 subdivisions — data/reference/regions/: each national authority's own list, kept exactly as published,
  with the rule that forms the ISO code from it (provenance.json): US — Census Bureau state FIPS/ANSI codes,
  'US-' + USPS code; BR — IBGE federative units, 'BR-' + sigla; CA — Statistics Canada SGC 2021 Table B, which states
  each province's ISO 3166-2 code. A country without a list here has no named regions.
  NUTS (EU regions) — Eurostat/GISCO NUTS 2021 (data/reference/geo/nuts3_eu_20m_2021.geojson); a NUTS code's parents
  are its prefixes (NUTS-1 three characters, NUTS-2 four), so every level is read from the level-3 file.

  Counties (US): the Census Bureau's 2020 county file — 'US-IA-19001' (ISO 3166-2 does not code counties: the state's
  ISO code + the 5-digit FIPS code).

A region code is valid only if it is here; a store or reader that names a region checks it with known().
"""
from __future__ import annotations

import csv
import io
import json
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path

DIR = Path(__file__).resolve().parents[2] / "data" / "reference" / "regions"
NUTS_FILE = Path(__file__).resolve().parents[2] / "data" / "reference" / "geo" / "nuts3_eu_20m_2021.geojson"


@lru_cache(maxsize=1)
def provenance() -> dict:
    return json.loads((DIR / "provenance.json").read_text(encoding="utf-8"))


def _us(raw: bytes) -> dict[str, str]:
    return {f"US-{r['STUSAB']}": r["STATE_NAME"] for r in csv.DictReader(io.StringIO(raw.decode("utf-8")), delimiter="|")}


def _br(raw: bytes) -> dict[str, str]:
    return {f"BR-{r['sigla']}": r["nome"] for r in json.loads(raw)}


class _TableB(HTMLParser):
    """The rows of the table that follows the 'Table B' caption of Statistics Canada's SGC 2021 introduction."""

    def __init__(self) -> None:
        super().__init__()
        self.seen_caption = self.in_table = self.in_cell = False
        self.rows: list[list[str]] = []
        self.text = ""

    def handle_starttag(self, tag, attrs):
        if tag == "table" and self.seen_caption and not self.rows:
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.rows.append([])
        elif self.in_table and tag in ("td", "th"):
            self.in_cell, self.text = True, ""

    def handle_endtag(self, tag):
        if self.in_table and tag in ("td", "th") and self.rows:
            self.rows[-1].append(" ".join(self.text.split()))
            self.in_cell = False
        elif tag == "table" and self.in_table:
            self.in_table = False

    def handle_data(self, data):
        if "Table B" in data and not self.rows:
            self.seen_caption = True
        if self.in_cell:
            self.text += data


def _ca(raw: bytes) -> dict[str, str]:
    """Table B: [SGC code, name, abbreviation, Canada Post code, ISO 3166-2 code, map] per province and territory."""
    t = _TableB()
    t.feed(raw.decode("utf-8"))
    out = {r[4]: r[1] for r in t.rows if len(r) >= 5 and r[0].isdigit() and r[4].startswith("CA-")}
    if len(out) != 13:
        raise ValueError(f"SGC 2021 Table B read {len(out)} provinces and territories — 13 expected")
    return out


def ca_sgc_codes() -> dict[str, str]:
    """{SGC province/territory code ('47'): ISO 3166-2 code ('CA-SK')} as Table B states them."""
    t = _TableB()
    t.feed((DIR / provenance()["files"]["CA"]["file"]).read_text(encoding="utf-8"))
    return {r[0]: r[4] for r in t.rows if len(r) >= 5 and r[0].isdigit() and r[4].startswith("CA-")}


_READERS = {"US": _us, "BR": _br, "CA": _ca}


@lru_cache(maxsize=None)
def of_country(cc: str) -> dict[str, str]:
    """{ISO 3166-2 code: name} of a country's subdivisions ({} when no official list is held)."""
    f = provenance()["files"].get(cc)
    return _READERS[cc]((DIR / f["file"]).read_bytes()) if f else {}


@lru_cache(maxsize=None)
def counties(cc: str) -> dict[str, str]:
    """{county code: name} — 'US-IA-19001' (state ISO 3166-2 + 5-digit FIPS) from the Census Bureau's 2020 county
    file; {} for a country without a county list here."""
    f = provenance().get("counties", {}).get(cc)
    if not f:
        return {}
    rows = csv.DictReader(io.StringIO((DIR / f["file"]).read_text(encoding="utf-8")), delimiter="|")
    return {f"{cc}-{r['STATE']}-{r['STATEFP']}{r['COUNTYFP']}": r["COUNTYNAME"] for r in rows}


@lru_cache(maxsize=1)
def nuts() -> dict[str, str]:
    """{NUTS code: name} — level 3 as published, levels 1 and 2 as the prefixes of the level-3 codes (name '' when the
    file does not carry it)."""
    out: dict[str, str] = {}
    for f in json.loads(NUTS_FILE.read_text(encoding="utf-8"))["features"]:
        p = f["properties"]
        out[p["NUTS_ID"]] = p.get("NUTS_NAME") or ""
        for n in (3, 4):
            out.setdefault(p["NUTS_ID"][:n], "")
    return out


def known(code: str) -> bool:
    """Is this a region code of the reference? ('' — the national figure — is not a region.)"""
    if not code:
        return False
    if "-" in code[:3]:
        cc = code.split("-", 1)[0]
        return code in of_country(cc) or code in counties(cc)
    return code in nuts()
