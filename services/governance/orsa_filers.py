"""Who reports the ORSA climate change scenario analysis (insurer_orsa_climate) — the filer rule of
services.governance.report_filers for an organisation of two or more reporting entities.

The analysis is part of the own-risk and solvency assessment and goes to the supervisor in the ORSA supervisory report.
Delegated Regulation (EU) 2015/35 names its two filers:
- each insurance or reinsurance undertaking, for itself: "the own-risk and solvency assessment supervisory report (‘ORSA
  supervisory report’) comprising the results of each regular own risk and solvency assessment performed by the insurance
  and reinsurance undertakings" (Art. 304(1)(c));
- the group: "Articles 304 to 311 of this Regulation shall apply to the information which participating insurance and
  reinsurance undertakings, insurance holding companies or mixed financial holding companies shall be required to submit
  to the group supervisor" (Art. 372(1)) — the group's ORSA supervisory report, on the deadline of Art. 312 without the
  six weeks other group reports get (Art. 373).
These are the filers of Solvency II nat-cat (services.governance.sii_filers): each group (a top entity with entities
below it) and each entity that files its own report; the reading of who is which is shared, not copied.

Not modelled: the single ORSA document — with the group supervisor's agreement, the group's assessment may cover its
subsidiaries' ("where applicable, information on the subsidiaries included in the own risk and solvency assessment as
referred to in the third subparagraph of Article 246(4) of Directive 2009/138/EC", Art. 372(2)(b)(ii)); the platform
records no such agreement, so each undertaking is offered its own. EIOPA Q&A on regulation (checked 2026-10-29: topic ORSA,
6 Q&As; keyword searches): none on who submits the ORSA supervisory report in a group; 1350 (final, submitted 5 Dec 2018)
on its timing, 3261 (final, 18 Feb 2025) on its content.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

FRAMEWORK = "insurer_orsa_climate"
DR = "02015R0035-20241114"
QUOTES = {
    "Del. Reg. 2015/35 Art. 304(1)(c)": (DR, "the own-risk and solvency assessment supervisory report (‘ORSA supervisory "
                                             "report’) comprising the results of each regular own risk and solvency "
                                             "assessment performed by the insurance and reinsurance undertakings"),
    "Del. Reg. 2015/35 Art. 372(1)": (DR, "Articles 304 to 311 of this Regulation shall apply to the information which "
                                          "participating insurance and reinsurance undertakings, insurance holding "
                                          "companies or mixed financial holding companies shall be required to submit to "
                                          "the group supervisor."),
    "Del. Reg. 2015/35 Art. 372(2)(b)(ii)": (DR, "where applicable, information on the subsidiaries included in the own "
                                                 "risk and solvency assessment as referred to in the third subparagraph of "
                                                 "Article 246(4) of Directive 2009/138/EC"),
    "Del. Reg. 2015/35 Art. 373": (DR, "the deadlines referred to in Article 312 shall be extended by 6 weeks, except for "
                                       "the ORSA supervisory report"),
}
_BASIS = {"group": "Delegated Regulation (EU) 2015/35 Art. 372(1) (the group's ORSA supervisory report)",
          "undertaking": "Delegated Regulation (EU) 2015/35 Art. 304(1)(c) (the undertaking's ORSA supervisory report)"}
BASIS = {FRAMEWORK: {
    "who": "each insurance undertaking for itself, or a group",
    "title": "Who reports the ORSA",
    "shows": "Each undertaking reports its own assessment; a group reports the group's. The whole organisation's book counts "
             "every entity in full, so it is neither.",
    "legal": "Delegated Regulation (EU) 2015/35, Art. 304(1)(c), Art. 372(1) and Art. 373.",
    "organisation": _BASIS["undertaking"]}}
NO_CHOICE = "a group or an undertaking of the entity structure"


def choices(session: Session, org_id: str, framework: str, period_end: date) -> list[dict]:
    """Each group, then each entity that files its own report — the undertakings and groups of sii_filers."""
    from services.governance import sii_filers
    return sii_filers.choices(session, org_id)


def owed(session: Session, org_id: str, framework: str, period_end: date) -> dict[str, str]:
    """The ORSA runs from its own conclusion, not a calendar date (filings.due_for_filing): nothing is owed by period;
    kept for the rule's shape."""
    return {c["entity_id"]: c["role"] for c in choices(session, org_id, framework, period_end)}


def record(session: Session, org_id: str, framework: str, entity_id: str, group: bool, period_end: date | None) -> dict:
    from services.governance import report_filers as RF
    name = next((e["name"] for e in RF.entities(session, org_id) if e["entity_id"] == entity_id), None)
    level = "group" if group else "undertaking"
    return {"level": level, "entity_id": entity_id, "name": name, "basis": _BASIS[level]}
