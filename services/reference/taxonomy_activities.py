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



def codes_of(ref: str | None) -> list[str]:
    """The activity codes of a stated activity reference ('CCM 7.7 / CCA 7.7 — Acquisition and ownership of buildings'
    → ['CCM 7.7', 'CCA 7.7']); none when the reference names no printed code."""
    head = (ref or "").split(" — ")[0]
    return [c for c in (" ".join(p.split()).upper() for p in head.split(" / ")) if c in _by_code()]


def _cited(phase: dict | None) -> list[tuple[str, str, str]]:
    """(act number, annex, section) for every section a phase-in cites: 'Delegated Regulation (EU) 2021/2139 Annex II'
    with '5.13' → ('2021/2139', 'Annex II', '5.13')."""
    out = []
    for where, sections in (((phase or {}).get("eligibility_only") or {}).get("activities") or {}).items():
        act, annex = where.rsplit(" Annex ", 1)
        out += [(act.split()[-1], f"Annex {annex}", s) for s in sections]
    return out


def _annex_objective(act_no: str, annex: str) -> str:
    for act in reference()["acts"].values():
        if act["short"].split("(EU) ")[-1].split()[0] == act_no and annex in (act.get("annexes") or {}):
            return act["annexes"][annex]["objective"]
    raise ValueError(f"a phase-in cites {annex} of {act_no}, which the activity reference does not map to an objective")


def eligibility_only(phase: dict | None) -> frozenset[str]:
    """The activity codes a spec's phase-in says are disclosed for eligibility only: every activity of the objectives
    it lists, and the sections it cites of an act's annexes (the act's own Articles say which objective an annex
    covers: acts[...].annexes). A cited section that matches no activity narrows nothing (see unmatched)."""
    return _eligibility_only(json.dumps((phase or {}).get("eligibility_only") or {}, sort_keys=True))


@lru_cache(maxsize=16)
def _eligibility_only(only_json: str) -> frozenset[str]:
    only = json.loads(only_json)
    objs = only.get("objectives")
    out = {a["code"] for a in activities() if objs == "all" or a["objective"] in (objs or [])}
    for act_no, annex, section in _cited({"eligibility_only": only}):
        code = f"{_annex_objective(act_no, annex).upper()} {section}"
        if code in _by_code():
            out.add(code)
    return frozenset(out)


def unmatched(phase: dict | None) -> list[dict]:
    """Sections a phase-in cites that match no activity, each with the reference's declared finding (a cited section
    with no finding on file raises: it is either a capture error or a new finding to declare)."""
    notes = {u["cited"]: u for u in reference().get("unmatched_citations") or []}
    out = []
    for act_no, annex, section in _cited(phase):
        if f"{_annex_objective(act_no, annex).upper()} {section}" in _by_code():
            continue
        key = next((k for k in notes if k.startswith(f"Section {section} of {annex} to ") and k.endswith(act_no)), None)
        if key is None:
            raise ValueError(f"a phase-in cites Section {section} of {annex} to {act_no}, which matches no activity "
                             "and has no declared finding in the activity reference")
        out.append(notes[key])
    return out
