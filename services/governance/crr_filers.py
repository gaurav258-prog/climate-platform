"""Who discloses ESG risks under Pillar 3 (bank_p3esg), as Regulation (EU) No 575/2013 (CRR) says — the filer rule of
services.governance.report_filers for an organisation that records its undertakings as reporting entities.

Part Eight applies to each institution on an individual basis (Art. 6(1)), but "No institution which is either a parent
undertaking or a subsidiary, and no institution included in the consolidation pursuant to Article 18, shall be required
to comply with the obligations laid down in Part Eight on an individual basis" (Art. 6(3)). Instead:
- "EU parent institutions shall comply with Part Eight on the basis of their consolidated situation" (Art. 13(1), first
  subparagraph): each group — a top entity with entities below it — files on its consolidated situation;
- "Large subsidiaries of EU parent institutions shall disclose the information specified in Articles ... 449a ... on an
  individual basis or, where applicable ..., on a sub-consolidated basis" (Art. 13(1), second subparagraph): a
  subsidiary files its own when it is stated to be a large institution (Art. 4(1)(146), (147)) for the period — the
  organisation's attested statement `large_institution` per subsidiary (the bank_p3esg catalog), made on the group's
  filing; a subsidiary with entities below it files on its sub-consolidated situation;
- an entity that is neither parent nor subsidiary (a top with nothing below it) is an institution on its own and files
  its own (Art. 6(1)). A branch is part of an undertaking, never a filer.

EBA Single Rulebook Q&A (checked 2026-10-29; keyword 449a, 49 Q&As): 2022_6652 (final, submitted 7 Dec 2022, published
10 Mar 2023) and 2023_6708 (final, submitted 30 Jan 2023, published 25 Aug 2023): institutions disclose "at the highest
level of consolidation in the EU, as regulated in Article 13 CRR", for "the undertakings included in the scope of
prudential consolidation (based on Art. 18 CRR)"; 2023_6695 (final, published 25 Aug 2023) the same. These predate
Regulation (EU) 2024/1623, which added Article 449a to the large subsidiaries' list of Art. 13(1) (consolidated text of
1 January 2025, held); no Q&A on large subsidiaries since. Not modelled: an EU parent included in a third-country
parent's equivalent disclosures (Art. 13(3)), and an entity's authorisation — each entity of the tree that is not a
branch is read as an institution.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

FRAMEWORK = "bank_p3esg"
CRR = "02013R0575-20250101"
KEY = "large_institution"                       # the statement per subsidiary (services.governance.datapoint_catalog)
CHOICES = {"large": "A large institution (Art. 4(1)(146) CRR)", "not_large": "Not a large institution"}
# each reading above, in the act's own words (data/sources/legal; checked word for word by tests/unit/test_report_filers.py)
QUOTES = {
    "CRR Art. 6(1)": (CRR, "Institutions shall comply with the obligations laid down in Parts Two, Three, Four, Seven, "
                           "Seven A and Eight of this Regulation and in Chapter 2 of Regulation (EU) 2017/2402 on an "
                           "individual basis"),
    "CRR Art. 6(3)": (CRR, "No institution which is either a parent undertaking or a subsidiary, and no institution "
                           "included in the consolidation pursuant to Article 18, shall be required to comply with the "
                           "obligations laid down in Part Eight on an individual basis."),
    "CRR Art. 13(1), first subparagraph": (CRR, "EU parent institutions shall comply with Part Eight on the basis of their "
                                                "consolidated situation."),
    "CRR Art. 13(1), second subparagraph": (CRR, "Large subsidiaries of EU parent institutions shall disclose the "
                                                 "information specified in Articles 437, 438, 440, 442, 449a, 449b, 450, "
                                                 "451, 451a and 453 on an individual basis or, where applicable in "
                                                 "accordance with this Regulation and Directive 2013/36/EU, on a "
                                                 "sub-consolidated basis."),
    "CRR Art. 4(1)(146)": (CRR, "‘large institution’ means an institution that meets any of the following conditions"),
    "CRR Art. 4(1)(147)": (CRR, "‘large subsidiary’ means a subsidiary that qualifies as a large institution"),
    "CRR Art. 449a(1)": (CRR, "Institutions shall disclose information on ESG risks"),
}
_BASIS = {"group": "Regulation (EU) No 575/2013 Art. 13(1), first subparagraph",
          "institution": "Regulation (EU) No 575/2013 Art. 6(1)",
          "large_subsidiary": "Regulation (EU) No 575/2013 Art. 13(1), second subparagraph",
          "not_owed": "Regulation (EU) No 575/2013 Art. 6(3): not required on an individual basis"}
BASIS = {FRAMEWORK: {
    "who": "a group on its consolidated situation, a large subsidiary, or an institution that is neither parent nor subsidiary",
    "title": "Who discloses ESG risks",
    "shows": "A group discloses on its consolidated situation, and a large subsidiary discloses its own; an institution that "
             "is neither a parent nor a subsidiary discloses its own. The whole organisation's book counts every entity in "
             "full, so it is none of these.",
    "legal": "Regulation (EU) No 575/2013, Art. 6(1) and (3), Art. 13(1); EBA Q&A 2022_6652 and 2023_6708.",
    "organisation": _BASIS["institution"]}}
NO_CHOICE = "a group or an institution of the entity structure"


def large(session: Session, org_id: str, period_end: date) -> dict[str, dict]:
    """The attested statements for the period, {subsidiary entity_id: {value, attested_by}}."""
    from services.governance.provided_data import attested_values
    return {v["member"]: {"value": v["value"], "attested_by": v.get("attested_by")}
            for v in attested_values(session, org_id, FRAMEWORK, period_end)
            if v["concept"] == KEY and v.get("member")}


def subsidiaries(ents: list[dict]) -> list[dict]:
    """The entities a statement is made for: each below a parent in the tree that is not a branch."""
    from services.governance.report_filers import is_branch
    return [e for e in ents if e["parent_entity_id"] is not None and not is_branch(e)]


def choices(session: Session, org_id: str, framework: str, period_end: date) -> list[dict]:
    """Each group, each institution on its own, then each subsidiary stated large — with its filing's role."""
    from services.governance import report_filers as RF
    ents = RF.entities(session, org_id)
    alone = [{"entity_id": e["entity_id"], "name": e["name"], "role": "solo"} for e in ents
             if e["parent_entity_id"] is None and not e["has_children"] and not RF.is_branch(e)]
    stated = large(session, org_id, period_end)
    subs = [{"entity_id": e["entity_id"], "name": e["name"], "role": "consolidated" if e["has_children"] else "solo"}
            for e in subsidiaries(ents) if (stated.get(e["entity_id"]) or {}).get("value") == "large"]
    return RF.groups(ents) + alone + subs


def owed(session: Session, org_id: str, framework: str, period_end: date) -> dict[str, str]:
    return {c["entity_id"]: c["role"] for c in choices(session, org_id, framework, period_end)}


def record(session: Session, org_id: str, framework: str, entity_id: str, group: bool, period_end: date | None) -> dict:
    """The filer an entity's book is for; a group's record lists its subsidiaries with their stated size class (the form
    section where they are stated)."""
    from services.governance import entities as E
    from services.governance import report_filers as RF
    ents = {e["entity_id"]: e for e in RF.entities(session, org_id)}
    e = ents[entity_id]
    stated = large(session, org_id, period_end) if period_end else {}
    if e["parent_entity_id"] is None:
        level = "group" if e["has_children"] else "institution"
    else:
        level = "large_subsidiary" if (stated.get(entity_id) or {}).get("value") == "large" else "not_owed"
    out = {"level": level, "entity_id": entity_id, "name": e["name"], "basis": _BASIS[level]}
    if level == "large_subsidiary" and group:
        out["basis"] += " (on its sub-consolidated situation)"
    if level == "group":
        tree = set(E.subtree_ids(session, org_id, entity_id))
        out["subsidiaries"] = [{"entity_id": s["entity_id"], "name": s["name"],
                                "stated": (stated.get(s["entity_id"]) or {}).get("value"),
                                "attested_by": (stated.get(s["entity_id"]) or {}).get("attested_by")}
                               for s in subsidiaries(list(ents.values())) if s["entity_id"] in tree]
    return out


def check_member(session: Session, org_id: str, member: str | None) -> None:
    """A statement names one of the organisation's subsidiaries (an entity below a parent, not a branch); ValueError else."""
    from services.governance import report_filers as RF
    if member not in {e["entity_id"] for e in subsidiaries(RF.entities(session, org_id))}:
        raise ValueError("not a subsidiary of the organisation's entity structure")


def statement_section(payload: dict | None) -> dict | None:
    """A group's filing: one row per subsidiary with the size class frozen with it and an entry for the period's
    statement (a choice, attested by a second person) — which decides the large subsidiaries' own disclosures."""
    f = (payload or {}).get("_filer") or {}
    if f.get("level") != "group":
        return None
    subs = f.get("subsidiaries") or []
    rows = [{"type": "row", "cells": [
        {"text": s["name"]},
        {"text": CHOICES.get(s.get("stated"), "—"), "key": f"{KEY}@{s['entity_id']}", "frozen_value": s.get("stated"),
         "supply": {"framework": FRAMEWORK, "key": KEY, "member": s["entity_id"], "choices": CHOICES}},
        {"text": s.get("attested_by") or "—"}]} for s in subs]
    unstated = [s["name"] for s in subs if not s.get("stated")]
    note = ("A large subsidiary discloses its own ESG risks (Art. 13(1) CRR, second subparagraph); the calendar owes it "
            "once its statement is approved." + (f" Not stated: {', '.join(unstated)}." if unstated else ""))
    return {"title": "Large subsidiaries", "key": KEY, "columns": ["Subsidiary", "Size class", "Attested by"],
            "col_sources": ["", "manual", ""], "rows": rows,
            "note": note if subs else "No subsidiary in the group's structure."}
