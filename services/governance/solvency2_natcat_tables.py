"""The Solvency II standard-formula nat-cat tables in force on a reference date, read from reference data only.

data/reference/solvency2_natcat_rules.json lists the versions of Delegated Regulation (EU) 2015/35 (as amended by
2019/981; as amended by 2026/269 from 30 January 2027) and, per version, the factor files (Annexes V-VIII, VIIIa),
the zone tables (Annexes IX, X, XXII-XXVI) and the Annex IX postal-code mapping. Nothing here is typed: a factor, a
weight, a correlation, a region list or a postal rule is read from those files, which were verified cell by cell
against the EU text. Also: Annex XIII (regions whose risks are not charged on premiums) and the declared readings.
"""
from __future__ import annotations

import json
import os
from datetime import date
from functools import lru_cache

from services.reference.eu_membership import members_iso2
from services.reference.iso_country import to_iso2

_DIR = os.path.join("data", "reference")
RULES_FILE = os.path.join(_DIR, "solvency2_natcat_rules.json")
REGIONAL_PERILS = ("windstorm", "earthquake", "flood", "hail")


class TablesMissing(RuntimeError):
    """A file the version names is absent or not marked verified."""


@lru_cache(maxsize=1)
def rules() -> dict:
    with open(RULES_FILE) as f:
        return json.load(f)


@lru_cache(maxsize=16)
def _load(name: str) -> dict | None:
    path = os.path.join(_DIR, name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def version(ref_date: date | None = None) -> dict:
    """The version entry in force on ref_date (default: today)."""
    d = (ref_date or date.today()).isoformat()
    for v in rules()["versions"]:
        a = v["applies"]
        if a["from"] <= d and (a["until"] is None or d <= a["until"]):
            return v
    raise TablesMissing(f"no Solvency II nat-cat version applies on {d}")


def peril_table(v: dict, peril: str) -> dict | None:
    """{region_order, regions{code: {name, q}}, correlation, iso2_to_region, citation} for a regional peril (and, in
    a version where subsidence is regional, for subsidence) — None when the version holds no such table."""
    if peril == "windstorm":
        f = _load(v["files"]["windstorm"])
        if not f or not f.get("verified"):
            raise TablesMissing(f"{v['files']['windstorm']} absent or unverified")
        return {**f, "citation": f.get("_citation", "Del. Reg. (EU) 2015/35, Art. 121 + Annex V")}
    f = _load(v["files"]["natcat"])
    if not f or not f.get("verified"):
        raise TablesMissing(f"{v['files']['natcat']} absent or unverified")
    return f.get(peril)


def zonal(v: dict, peril: str, region: str) -> dict | None:
    """The region's zone table {zones{key: {name, w}}, correlation, labels_verified} — None for a region without zones."""
    f = _load(v["files"]["zonal"])
    if not f or not f.get("verified"):
        raise TablesMissing(f"{v['files']['zonal']} absent or unverified")
    return (f.get(peril) or {}).get(region)


def annex_ix(v: dict) -> dict | None:
    """The version's Annex IX postal-code mapping (None until loaded: every zoned region then groups under Art. 90b)."""
    name = v["files"].get("annex_ix")
    return _load(name) if name else None


def in_annex_xiii(iso2: str | None) -> bool:
    """Annex XIII: Member States of the Union (outermost regions included — declared reading), AD IS LI MC NO SM CH VA."""
    c = to_iso2(iso2)
    if not c:
        return False
    r = rules()
    listed = set(r["other_regions"]["annex_xiii"]["iso2"])
    outermost = next((set(x["iso2"]) for x in r["interpretations"] if x["subject"] == "Outermost regions"), set())
    return c in members_iso2() or c in listed or c in outermost


def _normalise_key(k: str) -> str:
    return str(int(k)) if k.isdigit() else k


def zone_of(v: dict, peril: str, region: str, iso2: str | None, postal_code: str | None) -> str | None:
    """The Annex IX risk zone of a risk for a peril, from its country and postal code — None when Annex IX does not
    place it (no postal code, an administrative-unit region, a code the table does not list, or no mapping loaded)."""
    m = annex_ix(v)
    if not m:
        return None
    c = to_iso2(iso2)
    part = (m.get("part_of_region") or {}).get(c)            # AD, LI, MC, SM, VA: one zone of another region
    if part and part.get("region") == region:
        return _normalise_key(str(part["zone"]))
    spec = ((m.get(peril) or {}).get(region)) or {}
    pc = "".join(str(postal_code or "").upper().split())
    if not pc or not spec.get("map"):
        return None
    basis = spec.get("basis")
    if basis in ("postal_digits2", "postal_digits1", "postal_table"):     # the exact prefix, leading zeros kept
        n = spec["prefix_len"]
        key = pc[:n] if len(pc) >= n else None
    elif basis == "postal_letters2":
        key = pc[:2]
    elif basis == "uk_area":                                  # Annex IX (4): a digit in 2nd position → 1-letter zone
        key = pc[:1] if len(pc) > 1 and pc[1].isdigit() else pc[:2]
    else:                                                     # administrative unit / not a postal code: not placed
        return None
    if key is None or key in (spec.get("ambiguous") or {}):
        return None
    z = spec["map"].get(key)
    return _normalise_key(str(z)) if z is not None else None


def reading(subject: str) -> str:
    return next(x["reading"] for x in rules()["interpretations"] if x["subject"] == subject)
