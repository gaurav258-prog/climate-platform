"""Match incoming records to the live book: new, update, unchanged or ambiguous — never a silent guess.

Identity rules, strongest first:
  1. The customer's own asset id (external_ref). Same id → the same asset.
  2. For a live asset that has no id yet: same name (case-insensitive) AND within 250 m. The id is then attached,
     so the next file matches on it. (Names alone are not unique in real books, so a name never matches by itself.)
  3. More than one live asset satisfies rule 2 → ambiguous: the row needs a person to look at it.
Anything else is a new asset.

A blank value in the file never clears a value we already hold; only values the file gives can change a fact.

Within one file, two rows claiming the same asset (same id, or both matching the same live asset) is a duplicate:
the later row is rejected. Large changes to an existing asset (value moves more than 50%, or the location moves
more than 1 km) are flagged — principle 1 says the client's value wins, but a big difference needs a second person.
"""
from __future__ import annotations

import math
from typing import Optional

NAME_MATCH_RADIUS_M = 250.0
LARGE_VALUE_CHANGE = 0.50
LARGE_MOVE_M = 1000.0
_FLOAT_TOL = 1e-6


def _dist_m(a_lat, a_lon, b_lat, b_lon) -> float:
    if None in (a_lat, a_lon, b_lat, b_lon):
        return float("inf")
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def _norm(s: Optional[str]) -> str:
    return " ".join((s or "").lower().split())


def _same(a, b) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= max(_FLOAT_TOL, 1e-9 * max(abs(a), abs(b)))
    return str(a) == str(b)


def match(records: list[Optional[dict]], existing: list[dict], *, name_field: str, value_field: str,
          compare: tuple[str, ...]) -> list[dict]:
    """records: built records (None for rows already rejected). Returns one result per record:
    {"status": new|update|unchanged|ambiguous|duplicate|None, "entity_id", "diff": {field: [old, new]},
     "large": [reasons], "attach_ref": bool}"""
    by_ref = {e["external_ref"]: e for e in existing if e.get("external_ref")}
    by_name: dict[str, list[dict]] = {}
    for e in existing:
        by_name.setdefault(_norm(e.get(name_field)), []).append(e)

    claimed: dict[str, int] = {}      # live entity_id → first row index that claimed it
    seen_refs: dict[str, int] = {}
    out: list[dict] = []
    for i, rec in enumerate(records):
        if rec is None:
            out.append({"status": None})
            continue
        ref = rec.get("external_ref")
        if ref and ref in seen_refs:
            out.append({"status": "duplicate", "problem": f"asset id '{ref}' appears more than once in this file"})
            continue
        if ref:
            seen_refs[ref] = i

        target: Optional[dict] = None
        attach = False
        if ref and ref in by_ref:
            target = by_ref[ref]
        else:
            cands = [e for e in by_name.get(_norm(rec.get(name_field)), [])
                     if not e.get("external_ref") and _dist_m(e.get("latitude"), e.get("longitude"),
                                                                rec.get("latitude"), rec.get("longitude")) <= NAME_MATCH_RADIUS_M]
            if len(cands) > 1:
                out.append({"status": "ambiguous", "problem": f"{len(cands)} existing assets share this name and location",
                            "candidates": [c["entity_id"] for c in cands]})
                continue
            if cands:
                target, attach = cands[0], bool(ref)

        if target is None:
            out.append({"status": "new", "entity_id": None, "diff": {}, "large": []})
            continue
        if target["entity_id"] in claimed:
            out.append({"status": "duplicate", "problem": "another row in this file already updates the same asset"})
            continue
        claimed[target["entity_id"]] = i

        # a blank incoming value never clears a fact we hold — only values the file actually gives can change it
        diff = {f: [target.get(f), rec.get(f)] for f in compare
                if rec.get(f) is not None and not _same(target.get(f), rec.get(f))}
        large = []
        old_v, new_v = target.get(value_field), rec.get(value_field)
        if old_v and new_v is not None and abs(new_v - old_v) / abs(old_v) > LARGE_VALUE_CHANGE:
            large.append(f"value changes by {100 * (new_v - old_v) / abs(old_v):+.0f}%")
        moved = _dist_m(target.get("latitude"), target.get("longitude"), rec.get("latitude"), rec.get("longitude"))
        if moved > LARGE_MOVE_M and moved != float("inf"):
            large.append(f"location moves {moved / 1000:.1f} km")
        out.append({"status": "update" if diff else "unchanged", "entity_id": target["entity_id"], "diff": diff,
                    "large": large, "attach_ref": attach,
                    "moved": any(f in diff for f in ("latitude", "longitude", "plot_geometry"))})
    return out


def summarize(results: list[dict], names: list[Optional[str]]) -> dict:
    counts = {k: 0 for k in ("new", "update", "unchanged", "ambiguous", "duplicate")}
    large, updates = [], []
    for r, n in zip(results, names):
        st = r.get("status")
        if st in counts:
            counts[st] += 1
        if st == "update":
            if len(updates) < 25:
                updates.append({"name": n, "changes": {k: v for k, v in r["diff"].items()}})
            if r.get("large"):
                large.append({"name": n, "reasons": r["large"]})
    return {**counts, "updates": updates, "large_changes": large}
