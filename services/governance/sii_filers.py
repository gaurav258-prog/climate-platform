"""Who reports Solvency II natural catastrophe risk (S.27.01), as Implementing Regulation (EU) 2023/894 says — for the
filing scope, the filing calendar and the exports of the insurer_solvency report.

Two filers, and only two:
- an insurance or reinsurance undertaking, for itself: "template S. 27.01.01 of Annex I" (Art. 19(1)(s)(i)), identified
  by the "Identification code of the undertaking, using the Legal Entity Identifier (LEI)" (Annex II S.01.02 C0010/R0020);
- a group: "template S.27.01.04 of Annex I" (Art. 34(1)(s)), submitted by the participating undertaking, insurance holding
  company or mixed financial holding company "at the head of the insurance or reinsurance group" and identified by the
  "Identification code of the participating undertaking" (Annex III S.01.02 C0010/R0010, R0020) — the information they
  "shall be required to submit to the group supervisor" (Delegated Regulation (EU) 2015/35 Art. 372(1)), on the group's
  consolidated data (Art. 335; services.governance.group_solvency for the method-1 part).

An organisation with two or more reporting entities is, as a whole, neither: its whole book is every entity's book at
100 %, which is not one undertaking's data and not the group's consolidated data. So for such an organisation the calendar
owes no whole-organisation report — it owes one per group (each top entity with entities below it) and one per entity that
files its own report — and the whole-organisation scope is refused with the group and undertakings to choose from. With no
or one reporting entity the organisation is the undertaking, as before. Each freeze records its filer (`_filer`); a
whole-organisation filing without that record exports no template.

EIOPA Q&A on regulation, checked 2026-10-23 and 2026-10-25 (template S.01.01, S.01.02, S.27.01, S.32.01; topics scope of
group, group solvency requirement, LEIs): none on a report covering several undertakings that is neither one undertaking's
nor the group's. Q&A 2848 (revised, submitted 31 Oct 2023): an undertaking that is part of a group still reports its own
templates. Q&A 2109 (final, submitted 11 Feb 2020): sub-group supervision is "a decision made by the relevant NCAs" (Del.
Reg. Art. 358) — so only the top of a tree is owed a group report here; a parent lower down files when it is set to file.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

FRAMEWORK = "insurer_solvency"
ITS, DR = "32023R0894", "02015R0035-20241114"
# each reading above, in the act's own words (data/sources/legal; checked word for word by tests/unit/test_sii_filers.py)
QUOTES = {
    "ITS Art. 19(1)(s)(i)": (ITS, "for insurance and reinsurance undertakings other than captive insurance or captive "
                                  "reinsurance undertaking, template S. 27.01.01 of Annex I"),
    "ITS Annex II S.01.02 C0010/R0020": (ITS, "Identification code of the undertaking, using the Legal Entity Identifier (LEI)"),
    "ITS Art. 34(1)(s)": (ITS, "template S.27.01.04 of Annex I, specifying information on non-life catastrophe risk"),
    "ITS Annex III S.01.02 C0010/R0010": (ITS, "Legal name of the participating insurance and reinsurance undertaking or "
                                               "insurance holding company or mixed financial holding company at the head of "
                                               "the insurance or reinsurance group"),
    "ITS Annex III S.01.02 C0010/R0020": (ITS, "Identification code of the participating undertaking, using the Legal Entity "
                                               "Identifier (‘LEI’)"),
    "Del. Reg. Art. 372(1)": (DR, "participating insurance and reinsurance undertakings, insurance holding companies or mixed "
                                  "financial holding companies shall be required to submit to the group supervisor"),
}
UNDERTAKING = {"template": "S.27.01.01", "basis": "Implementing Regulation (EU) 2023/894 Art. 19(1)(s)(i)"}
GROUP = {"template": "S.27.01.04", "basis": "Implementing Regulation (EU) 2023/894 Art. 34(1)(s)"}


def _entities(session: Session, org_id: str) -> list[dict]:
    return [dict(r) for r in session.execute(text("""
        SELECT e.entity_id::text AS entity_id, e.name, e.parent_entity_id::text AS parent_entity_id, e.requires_solo_filing,
               EXISTS(SELECT 1 FROM reporting_entities c WHERE c.parent_entity_id = e.entity_id) AS has_children
        FROM reporting_entities e WHERE e.org_id = :o ORDER BY e.name, e.entity_id"""), {"o": org_id}).mappings()]


def is_filer(session: Session, org_id: str) -> bool:
    """Whether the organisation as a whole is a filer: it is the undertaking when it has no or one reporting entity."""
    return len(_entities(session, org_id)) < 2


def whole_org_refusal(session: Session, org_id: str, framework: str, entity_id: str | None) -> tuple[str, dict] | None:
    """(catalogue code, params) when a whole-organisation scope is not a filer's for this report, else None."""
    if framework != FRAMEWORK or entity_id is not None:
        return None
    ents = _entities(session, org_id)
    if len(ents) < 2:
        return None
    return "filing.refused.sii_whole_org", {"count": len(ents), "choices": ", ".join(c["name"] for c in choices(session, org_id))}


def choices(session: Session, org_id: str) -> list[dict]:
    """The filers a preparer chooses from: each group (top entity with entities below it), then each entity that files
    its own report — with the role its filing takes (entities.filing_role_for: an entity with entities below it
    consolidates them)."""
    ents = _entities(session, org_id)
    groups = [{"entity_id": e["entity_id"], "name": e["name"], "role": "consolidated"}
              for e in ents if e["parent_entity_id"] is None and e["has_children"]]
    seen = {g["entity_id"] for g in groups}
    own = [{"entity_id": e["entity_id"], "name": e["name"], "role": "consolidated" if e["has_children"] else "solo"}
           for e in ents if e["requires_solo_filing"] and e["entity_id"] not in seen]
    return groups + own


def owed(session: Session, org_id: str) -> dict[str | None, str]:
    """The reports the calendar owes for a period, {entity_id (None = the organisation): filing role}."""
    if is_filer(session, org_id):
        return {None: "whole_org", **{e["entity_id"]: "consolidated" if e["has_children"] else "solo"
                                      for e in _entities(session, org_id) if e["requires_solo_filing"]}}
    return {c["entity_id"]: c["role"] for c in choices(session, org_id)}


def record(session: Session, org_id: str, reporting_entity_id: str | None, group: bool) -> dict | None:
    """The filer a frozen book is for, frozen with it: a group's, an undertaking's, or — the whole organisation — the
    organisation's own when it is the undertaking. None when the whole-organisation book is not a filer's."""
    if reporting_entity_id is None and not group and not is_filer(session, org_id):
        return None
    return {"level": "group" if group else "undertaking", "entity_id": reporting_entity_id, **(GROUP if group else UNDERTAKING)}


def unrecorded_whole_org(payload: dict | None) -> bool:
    """A frozen whole-organisation book (no reporting entity, not a group's) without its filer record."""
    p = payload or {}
    return not p.get("_filer") and not p.get("_group_solvency") and not (p.get("_scope") or {}).get("reporting_entity_id")


def export_refusal(payload: dict | None, role: str | None) -> tuple[str, dict] | None:
    """(catalogue code, params) when a filing's frozen book is not established as one filer's — a whole-organisation
    filing frozen without its filer record (before it was kept, or when the organisation has two or more reporting
    entities) — else None. Its template (XBRL, workbook) is not produced."""
    if role == "whole_org" and unrecorded_whole_org(payload):
        return "filing.refused.sii_whole_org_frozen", {}
    return None
