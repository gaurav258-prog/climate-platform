"""Who files each entity-scoped report, as its acts say — for the filing scope, the filing calendar, the frozen record and
the exports. E343 read it for Solvency II nat-cat (services.governance.sii_filers); this is that reading for every
report whose act names its filers, one rule per report family:

  insurer_solvency           services.governance.sii_filers   an undertaking, a group (ITS (EU) 2023/894 Arts 19, 34)
  insurer_orsa_climate       services.governance.orsa_filers  the same filers (Directive 2009/138/EC Arts 45(1), 246(4);
                                                              Delegated Regulation (EU) 2015/35 Arts 304(1)(c), 372(1))
  insurer_recovery_stress    services.governance.irrd_filers  the ultimate parent for its group, an undertaking outside
                                                              a group plan, a subsidiary where required (Directive (EU)
                                                              2025/1 Arts 5, 7)
  bank_p3esg                 services.governance.crr_filers   an EU parent institution on its consolidated situation, a
                                                              large subsidiary, an institution on its own (CRR Arts 6, 13)
  bank_tcfd, reit_taxonomy   services.governance.csrd_filers  each undertaking subject to Art. 19a or 29a of Directive
                                                              2013/34/EU (Delegated Regulation (EU) 2021/2178 Art. 1(8),
                                                              (9)) — the undertakings of the ESRS statement

A report prepared for 'the whole organisation' takes every reporting entity's book at 100 %: not one undertaking's or
institution's own, and not a group's consolidated one (each act consolidates on its own rule). The organisation as a
whole is the filer only while it records no undertaking of its own (sii_filers.is_filer — the reading of E348 for
Solvency II, shared): once it records one, that entity reports for itself and the organisation is no second filer. So
the calendar owes each filer's report, one per (entity, role), and none for the whole organisation; the
whole-organisation scope is refused with the filers to choose from; every freeze records its filer (`_filer`); and a
whole-organisation report frozen without that record exports no template.

A rule module offers QUOTES (each reading in the act's own words, checked word for word against data/sources/legal),
choices(), owed() (both for an organisation of two or more entities), record() (an entity scope's filer) and BASIS (the
scope step's words); this module dispatches on the report and holds what they share.
"""
from __future__ import annotations

from datetime import date
from importlib import import_module

from sqlalchemy import text
from sqlalchemy.orm import Session

# the scope step's words for Solvency II nat-cat (its rule, services.governance.sii_filers, holds the quotes)
_SII_BASIS = {"title": "Who reports natural catastrophe risk",
              "shows": "Each undertaking reports its own figures; a group reports its consolidated figures. An undertaking at "
                       "the head of a group reports both. The whole organisation's book counts every entity in full, so it is "
                       "neither.",
              "legal": "Implementing Regulation (EU) 2023/894, Art. 19(1)(s)(i) and Art. 34(1)(s); Annex II and Annex III, "
                       "S.01.02."}
RULES = {"insurer_solvency": "sii_filers", "insurer_orsa_climate": "orsa_filers", "insurer_recovery_stress": "irrd_filers",
         "bank_p3esg": "crr_filers", "bank_tcfd": "csrd_filers", "reit_taxonomy": "csrd_filers"}
_SII = "insurer_solvency"


def governs(framework: str) -> bool:
    """Whether the report's filers come from its act (a rule here), not the framework-blind whole-organisation default."""
    return framework in RULES


def rule(framework: str):
    return import_module(f"services.governance.{RULES[framework]}")


def entities(session: Session, org_id: str) -> list[dict]:
    """The organisation's reporting entities with what a filer rule reads: its place in the tree, whether it files its own
    report (requires_solo_filing) and its kind (a branch is part of an undertaking, never one)."""
    return [dict(r) for r in session.execute(text("""
        SELECT e.entity_id::text AS entity_id, e.name, e.kind, e.parent_entity_id::text AS parent_entity_id,
               e.requires_solo_filing,
               EXISTS(SELECT 1 FROM reporting_entities c WHERE c.parent_entity_id = e.entity_id) AS has_children
        FROM reporting_entities e WHERE e.org_id = :o ORDER BY e.name, e.entity_id"""), {"o": org_id}).mappings()]


def groups(ents: list[dict]) -> list[dict]:
    """Each group: a top entity with entities below it, filing for its tree (the role entities.filing_role_for gives)."""
    return [{"entity_id": e["entity_id"], "name": e["name"], "role": "consolidated"}
            for e in ents if e["parent_entity_id"] is None and e["has_children"]]


def is_branch(e: dict) -> bool:
    return (e.get("kind") or "").strip().lower() == "branch"


def is_filer(session: Session, org_id: str) -> bool:
    """Whether the organisation as a whole is the filer: while it records no undertaking of its own (a branch is part of
    an undertaking, a group node stands for a group) — services.governance.sii_filers.is_filer, the one reading."""
    from services.governance.sii_filers import is_filer as records_none
    return records_none(session, org_id)


def choices(session: Session, org_id: str, framework: str, period_end: date) -> list[dict]:
    """The filers a preparer chooses from, [{entity_id, name, role}] — for an organisation of two or more entities."""
    if framework == _SII:
        return rule(framework).choices(session, org_id)
    return rule(framework).choices(session, org_id, framework, period_end)


def owed(session: Session, org_id: str, framework: str, period_end: date) -> set[tuple[str | None, str]]:
    """The reports the calendar owes for a period, as (entity_id — None = the organisation, filing role)."""
    if framework == _SII:
        return rule(framework).owed(session, org_id)
    if is_filer(session, org_id):
        return {(None, "whole_org")}
    return set(rule(framework).owed(session, org_id, framework, period_end).items())


def due(framework: str, undertaking_due, role: str):
    """A report's deadline for its role: Solvency II nat-cat's group report 6 weeks after an undertaking's
    (sii_filers.due); every other report's is its calendar date whatever the filer."""
    if framework == _SII:
        return rule(framework).due(undertaking_due, role)
    return undertaking_due


def whole_org_refusal(session: Session, org_id: str, framework: str, entity_id: str | None,
                      period_end: date) -> tuple[str, dict] | None:
    """(catalogue code, params) when the whole-organisation scope is no filer's for this report, else None."""
    if not governs(framework) or entity_id is not None:
        return None
    if framework == _SII:
        return rule(framework).whole_org_refusal(session, org_id, framework, entity_id)
    if is_filer(session, org_id):
        return None
    from services.governance.filings import FRAMEWORKS
    names = ", ".join(c["name"] for c in choices(session, org_id, framework, period_end))
    return "filing.refused.whole_org_no_filer", {"report": FRAMEWORKS[framework]["label"],
                                                 "choices": names or rule(framework).NO_CHOICE,
                                                 "who": rule(framework).BASIS[framework]["who"]}


def record(session: Session, org_id: str, framework: str, reporting_entity_id: str | None, group: bool,
           period_end: date | None) -> dict | None:
    """The filer a frozen book is for, frozen with it (`_filer`); None for a whole-organisation book that is no filer's."""
    if framework == _SII:
        return rule(framework).record(session, org_id, reporting_entity_id, group)
    if reporting_entity_id is None:
        if not is_filer(session, org_id):
            return None
        return {"level": "organisation", "entity_id": None, "basis": rule(framework).BASIS[framework]["organisation"]}
    return rule(framework).record(session, org_id, framework, reporting_entity_id, group, period_end)


def unrecorded_whole_org(payload: dict | None) -> bool:
    """A frozen whole-organisation book (no reporting entity, not a group's) without its filer record."""
    from services.governance.sii_filers import unrecorded_whole_org as sii
    return sii(payload)


def export_refusal(framework: str, payload: dict | None, role: str | None) -> tuple[str, dict] | None:
    """(catalogue code, params) when a filing's template is not one filer's — a whole-organisation report frozen without
    its filer record (before it was kept, or for an organisation of two or more entities) — else None."""
    if not governs(framework):
        return None
    if framework == _SII:
        return rule(framework).export_refusal(payload, role)
    if role == "whole_org" and unrecorded_whole_org(payload):
        from services.governance.filings import FRAMEWORKS
        return "filing.refused.whole_org_frozen", {"report": FRAMEWORKS[framework]["label"]}
    return None


def scope_basis(framework: str) -> dict | None:
    """What the scope step says about who reports this report: {title, shows, legal} in customer words."""
    if not governs(framework):
        return None
    b = _SII_BASIS if framework == _SII else rule(framework).BASIS[framework]
    return {"title": b["title"], "shows": b["shows"], "legal": b["legal"]}


def filers(session: Session, org_id: str, framework: str, period_end: date) -> dict:
    """Who a screen offers for a ruled report: the organisation itself when it is the filer, else its filers, with the
    report's words on who reports it."""
    org = not governs(framework) or is_filer(session, org_id)
    return {"framework": framework, "organisation": org,
            "filers": [] if org else choices(session, org_id, framework, period_end), "scope_basis": scope_basis(framework)}


def section(framework: str, payload: dict | None) -> dict | None:
    """The official form's 'Who reports' section: the filer the book was frozen for, or why it is not one filer's."""
    if not governs(framework) or framework == _SII:        # S.27.01's own form says it (services.governance.s2701_forms)
        return None
    p = payload or {}
    f = p.get("_filer")
    if f is None and not unrecorded_whole_org(p):
        return None
    if f is None:
        note = ("Not exported: frozen for the whole organisation without a record that it is the filer — refresh the draft, "
                "or prepare the report for each filer.")
        rows = [{"type": "row", "cells": [{"text": "The whole organisation"}, {"text": "Not one filer's report"}, {"text": "—"}]}]
    else:
        note = None
        rows = [{"type": "row", "cells": [{"text": f.get("name") or ("The organisation" if f.get("entity_id") is None else "—")},
                                          {"text": LEVELS.get(f.get("level"), "—")}, {"text": f.get("basis") or "—"}]}]
    out = {"title": "Who reports", "key": "filer", "columns": ["Reported for", "As", "Basis"], "rows": rows}
    if note:
        out["note"] = note
    return out


LEVELS = {"organisation": "The organisation (its only undertaking)", "group": "A group, on its consolidated figures",
          "undertaking": "An undertaking, for itself", "institution": "An institution, for itself",
          "large_subsidiary": "A large subsidiary, for itself", "not_owed": "Not owed — prepared by choice",
          "subsidiary_on_request": "A subsidiary, where its supervisor requires its own"}
