"""EUDR reference data — Annex I of Regulation (EU) 2023/1115 by date, and the Art. 29 country classification.

Read from data/reference/eudr (annex_i.json, country_risk.json); every description, note and country name there is
quoted from the stored official texts (services.reference.legal_texts) and checked in tests/unit/test_eudr_refdata.py.

Scope matching follows the printed codes only:
  * a printed heading/subheading covers every code that starts with it (4-digit 1801 covers 1801 00 00);
  * never the reverse: a code shorter than the printed entry (4-digit 1201 against 1201 90 00) is not decided → None;
  * an 'ex' entry lists only part of its heading, so the product's own description decides → None with the
    printed description;
  * no entry → False.
"""
from __future__ import annotations

import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path

from services.reference.iso_country import ISO_ALPHA2, to_iso2

DIR = Path(__file__).resolve().parents[2] / "data" / "reference" / "eudr"
ACT_1093 = "Commission Implementing Regulation (EU) 2025/1093 (CELEX 32025R1093), Art. 1"


@lru_cache(maxsize=1)
def _annex() -> dict:
    return json.loads((DIR / "annex_i.json").read_text())


@lru_cache(maxsize=1)
def _countries() -> dict:
    return json.loads((DIR / "country_risk.json").read_text())


def annex_i(on: date) -> dict:
    """The Annex I version that applies on `on` (ValueError before the Regulation entered into force)."""
    d = on.isoformat()
    for v in _annex()["versions"]:
        if v["applies_from"] <= d and (v["until"] is None or d <= v["until"]):
            return v
    raise ValueError(f"Annex I of Regulation (EU) 2023/1115 is not in force on {d}")


def _digits(hs_code: str) -> str:
    code = re.sub(r"[\s.]", "", str(hs_code or ""))
    if not code.isdigit() or len(code) not in (2, 4, 6, 8, 10):
        raise ValueError(f"not an HS/CN code: {hs_code!r}")
    return code


def scope(hs_code: str, on: date) -> dict:
    """Whether a product code falls under Annex I on a date: in_scope True | False | None (see module docstring)."""
    code = _digits(hs_code)
    v = annex_i(on)
    covering = [e for e in v["entries"] if code.startswith(e["code"])]
    narrower = [e for e in v["entries"] if e["code"].startswith(code) and e["code"] != code]
    base = {"version": v["id"], "source_celex": v["source_celex"], "general_exclusions": v["general_exclusions"]}
    if covering:
        e = max(covering, key=lambda x: len(x["code"]))
        notes = list(e["notes"]) + ([v["commodity_notes"][e["commodity"]]] if e["commodity"] in v["commodity_notes"] else [])
        out = {**base, "entry": e, "ex": e["ex"], "description": e["description"], "notes": notes}
        if e.get("application_ambiguous"):
            return {**out, "in_scope": None, "why": e["application_note"]}
        if e["ex"]:
            return {**out, "in_scope": None,
                    "why": f"printed as 'ex {e['printed_code'].replace('ex ', '')}': only the part of the heading "
                           f"described applies — the product's own description decides against: {e['description']}"}
        return {**out, "in_scope": True,
                "why": f"{code} falls under the printed entry {e['printed_code'] or e['code']} ({e['commodity']})"}
    if narrower:
        printed = ", ".join(e["printed_code"] or e["code"] for e in narrower)
        return {**base, "in_scope": None, "entry": None, "ex": None, "entries": narrower,
                "why": f"Annex I lists only narrower codes under {code} ({printed}); a {len(code)}-digit code "
                       f"cannot be placed against them — give the full code"}
    return {**base, "in_scope": False, "entry": None, "ex": None,
            "why": f"no Annex I entry covers {code} in version {v['id']}"}


def country_risk(iso2: str, on: date | None = None) -> dict | None:
    """'high' | 'low' | 'standard' under Implementing Regulation (EU) 2025/1093 (in force from 26.5.2025).
    None for a code that is not ISO 3166-1 alpha-2, or for a date before the classification entered into force."""
    code = to_iso2(iso2)
    if not code or code not in ISO_ALPHA2 or code in ("EU", "XK"):
        return None
    doc = _countries()
    if on is not None and on.isoformat() < doc["dates"]["in_force_from"]:
        return None
    for cls in ("high", "low"):
        hit = next((r for r in doc[cls] if r["iso2"] == code), None)
        if hit:
            return {"risk": cls, "printed_name": hit["name"], "act": ACT_1093, "quote": doc["article_1"]["quote_1"]}
    return {"risk": "standard", "printed_name": None, "act": ACT_1093, "quote": doc["article_1"]["quote_2"]}
