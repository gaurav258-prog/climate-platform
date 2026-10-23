"""A group's method of calculating group solvency, per related undertaking — method 1, accounting consolidation
(Directive 2009/138/EC Art. 230), or method 2, deduction and aggregation (Art. 233), chosen "in relation to a related
undertaking" (Delegated Regulation (EU) 2015/35 Art. 328(1)).

The group states each related undertaking's method for a reporting period under four eyes: the provided value
'group_solvency_method' of the insurer_solvency report, stated for the group, one per related undertaking
(services.governance.provided_data). Nothing is assumed. From the statements:
- method 1 for every one: method 1 exclusively — S.27.01.04 on the whole consolidated book.
- method 2 for every one: method 2 exclusively — S.27.01.04 does not apply (ITS (EU) 2023/894 Annex III S.27.01 (c));
  S.01.01.04 reports it 'Not reported as Method 2 is used exclusively' (EIOPA Q&A 963, final, 6 Feb 2017).
- both: a combination — S.27.01.04 carries only the part of the group calculated with method 1 (Annex III S.27.01 (b);
  Del. Reg. Art. 341). A method-2 undertaking's book leaves the consolidated data: its individual requirements are in
  S.33.01.04 "regardless of the method" (Annex III S.33.01; EIOPA Q&A 22, final) and its SCR in S.25.01.04 R0560
  (EIOPA Q&A 180, final) — templates of the group's own package — and its S.27.01.01 is its own solo report.
A related undertaking whose method is not stated leaves the group's method unknown. A method-1 undertaking held through a
method-2 undertaking is a named gap: neither the ITS nor an EIOPA Q&A (checked 2026-10-23) says how its data enters the
consolidated data. In both cases no S.27.01.04 is exported, with the reason.

Which undertakings: every one in the group's tree whose book the Solvency II method-1 consolidation takes in (full or
proportional, Del. Reg. Art. 335(1)(a)-(c)); an equity-method holding (Art. 335(1)(d)) has no book in it. A branch is
part of its undertaking (Directive Art. 13(11)) and follows its method; it is never asked for one.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

FRAMEWORK = "insurer_solvency"
KEY = "group_solvency_method"
CHOICES = {"method_1": "Method 1 — accounting consolidation", "method_2": "Method 2 — deduction and aggregation"}


class GroupSolvencyError(ValueError):
    """A statement refused: `kind` 'group' (not stated for a group) or 'related' (not one of its related undertakings)."""

    def __init__(self, message: str, kind: str):
        super().__init__(message)
        self.kind = kind


def _tree(session: Session, org_id: str, group_id: str) -> dict[str, dict]:
    from services.governance import entities as E
    ids = E.subtree_ids(session, org_id, group_id)
    rows = session.execute(text("""
        SELECT entity_id::text, name, kind, parent_entity_id::text FROM reporting_entities
        WHERE org_id = :o AND entity_id::text = ANY(:ids)"""), {"o": org_id, "ids": ids}).mappings().all()
    return {r["entity_id"]: dict(r) for r in rows}


def _undertaking_of(tree: dict, eid: str, group_id: str) -> str:
    """The undertaking an entity is part of: itself, or for a branch the nearest ancestor that is not a branch."""
    cur = eid
    while cur != group_id and (tree[cur]["kind"] or "").strip().lower() == "branch" and tree[cur]["parent_entity_id"] in tree:
        cur = tree[cur]["parent_entity_id"]
    return cur


def related_undertakings(session: Session, org_id: str, group_id: str) -> list[dict]:
    """The related undertakings whose method the group states: in its tree, not the group itself, not a branch, with a
    book the method-1 consolidation takes in (weight > 0)."""
    from services.governance import entities as E
    tree = _tree(session, org_id, group_id)
    w = E.ownership_weights(session, org_id, root_entity_id=group_id, regime=E.regime_for(FRAMEWORK))
    return sorted(({"entity_id": e, "name": r["name"], "parent_entity_id": r["parent_entity_id"]}
                   for e, r in tree.items() if e != group_id and (r["kind"] or "").strip().lower() != "branch"
                   and w.get(e, 0) > 0), key=lambda x: x["name"])


def check_member(session: Session, org_id: str, group_id: str | None, member: str | None) -> dict:
    """The related undertaking a statement names, or GroupSolvencyError: stated for a group, of one of its related
    undertakings."""
    if not group_id:
        raise GroupSolvencyError("the method is stated for a group", "group")
    und = {u["entity_id"]: u for u in related_undertakings(session, org_id, group_id)}
    if member not in und:
        raise GroupSolvencyError("not an undertaking whose figures the group consolidates", "related")
    return und[member]


def statement(session: Session, org_id: str, group_id: str, period_end: date) -> dict:
    """The group's method for the period from its attested statements: method ('method_1' / 'method_2' / 'combination'
    / None), status ('complete' / 'not_stated' / 'nested'), each related undertaking with its stated method and who
    attested it, and the undertakings S.27.01.04 leaves out (method 2, with their branches). Frozen with the filing."""
    from services.governance.provided_data import attested_values
    tree = _tree(session, org_id, group_id)
    und = related_undertakings(session, org_id, group_id)
    stated = {v["member"]: v for v in attested_values(session, org_id, FRAMEWORK, period_end, reporting_entity_id=group_id)
              if v["concept"] == KEY and v["member"]}
    rows = [{**u, "method": (stated.get(u["entity_id"]) or {}).get("value"),
             "attested_by": (stated.get(u["entity_id"]) or {}).get("attested_by"),
             "attested_at": (stated.get(u["entity_id"]) or {}).get("attested_at")} for u in und]
    method_of = {r["entity_id"]: r["method"] for r in rows}
    not_stated = [r["name"] for r in rows if r["method"] not in CHOICES]
    nested = []
    for r in rows:
        if r["method"] != "method_1":
            continue
        cur = tree[r["entity_id"]]["parent_entity_id"]
        while cur and cur != group_id and cur in tree:
            if method_of.get(cur) == "method_2":
                nested.append({"undertaking": r["name"], "held_through": tree[cur]["name"]})
                break
            cur = tree[cur]["parent_entity_id"]
    methods = {r["method"] for r in rows if r["method"] in CHOICES}
    method = None if not_stated or not methods else ("combination" if len(methods) > 1 else next(iter(methods)))
    # no related undertaking with a consolidated book (only branches, or equity holdings): no group method to state
    status = "no_related" if not rows else "not_stated" if not_stated else "nested" if nested else "complete"
    excluded = sorted(e for e in tree if e != group_id and method_of.get(_undertaking_of(tree, e, group_id)) == "method_2")
    return {"group_entity_id": group_id, "group_name": tree[group_id]["name"], "period_end": str(period_end)[:10],
            "method": method, "status": status, "undertakings": rows, "not_stated": not_stated, "nested": nested,
            "excluded_from_template": excluded if method == "combination" and status == "complete" else []}


def part_weights(weights: dict[str, float], st: dict) -> dict[str, float]:
    """The consolidation weights of the part of the group S.27.01.04 reports: with a complete combination of methods,
    each method-2 undertaking's book (and its branches') leaves; otherwise the weights as they are."""
    out = dict(weights)
    for e in st.get("excluded_from_template") or []:
        out[e] = 0.0
    return out


def group_lines(payload: dict | None) -> list[str]:
    """The frozen statement in words, for the form's notes and the workbook's Basis sheet."""
    st = (payload or {}).get("_group_solvency")
    if not st:
        return []
    word = {"method_1": "method 1 for every related undertaking", "method_2": "method 2 for every related undertaking",
            "combination": "a combination of methods 1 and 2 — this template reports the method-1 part only"}
    lines = [f"{st['group_name']}: {word.get(st['method'], 'not stated')}"]
    lines += [f"{u['name']}: {CHOICES.get(u['method'], 'not stated')}" for u in st["undertakings"]]
    lines += [f"{x['undertaking']} (method 1) is held through {x['held_through']} (method 2): not reported — no text "
              "says how it enters the consolidated data" for x in st.get("nested") or []]
    return lines


def section(payload: dict | None) -> dict | None:
    """The statement as a form section: one row per related undertaking with its frozen method and an entry for the
    period's statement (a choice, attested by a second person)."""
    st = (payload or {}).get("_group_solvency")
    if not st:
        return None
    rows = [{"type": "row", "cells": [
        {"text": u["name"]},
        {"text": CHOICES.get(u["method"], "—"), "key": f"{KEY}@{u['entity_id']}", "frozen_value": u["method"],
         "supply": {"framework": FRAMEWORK, "key": KEY, "member": u["entity_id"], "choices": CHOICES,
                    "reporting_entity_id": st["group_entity_id"]}},
        {"text": u["attested_by"] or "—"}]} for u in st["undertakings"]]
    head = {"complete": None, "no_related": "No related undertaking with a consolidated book.",
            "not_stated": "Method not stated for: " + ", ".join(st["not_stated"]),
            "nested": "; ".join(f"{x['undertaking']} (method 1) is held through {x['held_through']} (method 2)"
                                for x in st["nested"])}[st["status"]]
    return {"title": "Group solvency method of each related undertaking", "key": "group_solvency_method",
            "columns": ["Related undertaking", "Method", "Attested by"], "col_sources": ["", "manual", ""],
            "rows": rows, "note": " ".join(x for x in (group_lines(payload)[0], head) if x)}
