"""The economic activities of the EU Taxonomy — one reference list (data/reference/taxonomy/activities.json), captured
from the Delegated Acts (2021/2139 with 2022/1214 and 2023/2485, and 2023/2486) and independently second-passed.

Each activity has its printed code ('CCM 7.7'), title, objective, sector, category (transitional / enabling) and the
NACE codes the act itself associates with it. Those NACE lists are indicative — the acts say an activity 'could be
associated with several NACE codes, in particular …' — so a NACE code narrows the activities an undertaking may
perform; it decides the activity only where every activity listing it is the same activity (the same section under
several objectives, e.g. CCM 7.7 and CCA 7.7 'Acquisition and ownership of buildings').
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_FILE = Path(__file__).resolve().parents[2] / "data" / "reference" / "taxonomy" / "activities.json"


@lru_cache(maxsize=1)
def reference() -> dict:
    return json.loads(_FILE.read_text())


def activities() -> list[dict]:
    return reference()["activities"]


@lru_cache(maxsize=1)
def _by_code() -> dict[str, dict]:
    return {a["code"]: a for a in activities()}


def by_code(code: str) -> dict | None:
    return _by_code().get(" ".join(code.split()).upper())


def _digits(printed: str) -> str:
    """A printed NACE code as its numeric path: 'C25' → '25', 'C33.15' → '3315', 'A2' → '02' (a single-digit division
    is zero-padded), 'C.23.61' → '2361', '26.3' → '263'. Codes are kept as the acts print them; this only reads them."""
    s = printed.strip().upper()
    letter = bool(re.match(r"^[A-U]", s))
    parts = [p for p in re.split(r"[.\s]+", re.sub(r"^[A-U]\.?", "", s)) if p]
    if not parts or not all(p.isdigit() for p in parts):
        return ""
    if letter and len(parts[0]) == 1:
        parts[0] = parts[0].zfill(2)
    return "".join(parts)


@lru_cache(maxsize=1)
def _index() -> list[tuple[str, dict]]:
    return [(d, a) for a in activities() for code in a.get("nace") or [] if (d := _digits(code))]


def candidates(nace_code: str | None) -> list[dict]:
    """The activities whose printed NACE codes cover this NACE code (a printed division covers its groups and classes)."""
    from services.reference import nace as _nace
    hit = _nace.lookup(nace_code) if nace_code else None
    if not hit:
        return []
    mine = hit["dotted"].replace(".", "")
    seen, out = set(), []
    for d, a in _index():
        if mine.startswith(d) and a["code"] not in seen:
            seen.add(a["code"])
            out.append(a)
    return out


def activity_for(nace_code: str | None) -> dict:
    """{'status': 'determined' | 'not_determined' | 'none', 'activities': [...], 'section': ..., 'title': ...}: the
    activity a NACE code decides, when every activity listing it is the same section and title."""
    cands = candidates(nace_code)
    if not cands:
        return {"status": "none", "activities": []}
    sections = {(a["section"], a["title"].strip().lower()) for a in cands}
    if len(sections) == 1:
        a = cands[0]
        return {"status": "determined", "activities": cands, "section": a["section"], "title": a["title"],
                "codes": [c["code"] for c in cands]}
    return {"status": "not_determined", "activities": cands}
