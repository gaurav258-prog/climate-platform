"""Who reports the ORSA climate change scenario analysis (insurer_orsa_climate) — the filer rule of
services.governance.report_filers for an organisation that records its undertakings as reporting entities.

The analysis is part of the own-risk and solvency assessment: "every insurance undertaking and reinsurance undertaking
shall conduct its own risk and solvency assessment" (Directive 2009/138/EC Art. 45(1)), and the participating undertaking
or holding company undertakes it "at the level of the group" (Art. 246(4); Directive (EU) 2025/2 widens what the group
assessment covers, not who makes it). It goes to the supervisor in the ORSA supervisory report, whose two filers
Delegated Regulation (EU) 2015/35 names:
- each insurance or reinsurance undertaking, for itself: "the own-risk and solvency assessment supervisory report (‘ORSA
  supervisory report’) comprising the results of each regular own risk and solvency assessment performed by the insurance
  and reinsurance undertakings" (Art. 304(1)(c));
- the group: "Articles 304 to 311 of this Regulation shall apply to the information which participating insurance and
  reinsurance undertakings, insurance holding companies or mixed financial holding companies shall be required to submit
  to the group supervisor" (Art. 372(1)) — the group's ORSA supervisory report, on the deadline of Art. 312 without the
  six weeks other group reports get (Art. 373).
These are the filers of Solvency II nat-cat (services.governance.sii_filers): each group (a top entity with an undertaking
below it) and each entity that files its own report; the reading of who is which is shared, not copied.

An insurance undertaking at the head of a group owes both, as for nat-cat (E348): its own assessment (Art. 45(1) binds
"every insurance undertaking"; "the administrative, management or supervisory body of each insurance and reinsurance
undertaking within the group shall remain responsible for its own compliance with all requirements", Art. 246(1) as
replaced by Directive (EU) 2025/2) on its own book — itself and its branches, never an undertaking below it — and the
group's on the group's book. Two reports of one entity, told apart by their role ('solo' = its own, 'consolidated' = the
group's): filings._OWN_BOOK holds the ORSA beside nat-cat.

The single ORSA document does not cover the head's own assessment: with the group supervisor's agreement the group may
"undertake any assessments required pursuant to Article 45 at the level of the group and at the level of any subsidiary
in the group at the same time, and may produce a single document covering all the assessments" (Art. 246(4), third
subparagraph) — the group's and its subsidiaries', not the participating undertaking's own; and even then "the exercise
of that option shall not exempt the subsidiaries concerned" (fifth subparagraph). So a head undertaking's own ORSA is
always a report of its own. A subsidiary's inclusion is the group's statement of its supervisor's agreement, not
recorded here (named, not built): each subsidiary is offered its own.

When: "annually, and without any delay following any significant change in their risk profile" (Art. 45(5) as replaced by
Directive (EU) 2025/2, applied "from 30 January 2027", its Art. 4(1)); the report "within 2 weeks after concluding the
assessment" (Del. Reg. Art. 312(1)(b)). The day of the conclusion is the undertaking's: EIOPA Q&A 1350 — "the undertaking
decides when to perform the regular ORSA". So the calendar owes each filer's ORSA every period, its date the filing's
conclusion plus two weeks once one is prepared, none before (filings.ensure_filer_obligations). Not modelled (named): the
two-yearly assessment a small and non-complex or a captive undertaking may choose (Art. 45(5), second subparagraph).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

FRAMEWORK = "insurer_orsa_climate"
DR, SII, DIR2 = "02015R0035-20241114", "02009L0138-20250117", "32025L0002"
QUOTES = {
    "Directive 2009/138/EC Art. 45(1)": (SII, "As part of its risk-management system every insurance undertaking and "
                                              "reinsurance undertaking shall conduct its own risk and solvency assessment."),
    "Directive 2009/138/EC Art. 246(4), first subparagraph": (SII, "Member States shall require the participating insurance "
                                                                   "undertaking or reinsurance undertaking, the insurance "
                                                                   "holding company or the mixed financial holding company to "
                                                                   "undertake at the level of the group the assessment "
                                                                   "required by Article 45."),
    "Directive 2009/138/EC Art. 246(4), third subparagraph": (SII, "undertake any assessments required pursuant to Article 45 "
                                                                   "at the level of the group and at the level of any "
                                                                   "subsidiary in the group at the same time, and may produce "
                                                                   "a single document covering all the assessments"),
    "Directive 2009/138/EC Art. 246(4), fifth subparagraph": (SII, "The exercise of that option shall not exempt the "
                                                                   "subsidiaries concerned from the obligation to ensure that "
                                                                   "the requirements of Article 45 are met."),
    "Directive 2009/138/EC Art. 246(1), as replaced by Directive (EU) 2025/2 Art. 1(88)(a)":
        (DIR2, "The administrative, management or supervisory body of each insurance and reinsurance undertaking within the "
               "group shall remain responsible for its own compliance with all requirements, as specified in Article 40 and "
               "Article 213(1), second subparagraph."),
    "Directive 2009/138/EC Art. 45(5), as replaced by Directive (EU) 2025/2 Art. 1(23)(d)":
        (DIR2, "Insurance and reinsurance undertakings shall perform the assessment referred to in paragraph 1 annually, and "
               "without any delay following any significant change in their risk profile."),
    "Directive (EU) 2025/2 Art. 4(1)": (DIR2, "They shall apply those measures from 30 January 2027."),
    "Del. Reg. 2015/35 Art. 304(1)(c)": (DR, "the own-risk and solvency assessment supervisory report (‘ORSA supervisory "
                                             "report’) comprising the results of each regular own risk and solvency "
                                             "assessment performed by the insurance and reinsurance undertakings"),
    "Del. Reg. 2015/35 Art. 312(1)(b)": (DR, "the ORSA supervisory report referred to in Article 304(1)(c) within 2 weeks "
                                             "after concluding the assessment"),
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
# EIOPA Q&A on regulation read for this reading, each with its status and date of submission. On 2026-10-31 the archive's
# filtered search returned its unfiltered list, so the Q&As EIOPA's Solvency II Single Rulebook links to each article were
# read: Directive Art. 45 (50, 51), Art. 246 (none); Del. Reg. Art. 304 (1350, 1082, 1123), 306 (none), 312 (1350),
# 359 (none), 372 (460), 373 (none); with E350's topic search (ORSA, 2026-10-29). None on a head undertaking's own ORSA
# beside the group's, or on what the single document may cover.
QA = {
    "checked": ["2026-10-29", "2026-10-31"],
    "read": {
        "1350": ("Final", "05 Dec 2018", "'the undertaking decides when to perform the regular ORSA'; the report within 2 "
                                         "weeks after concluding the assessment (Art. 312(1)(b))"),
        "50": ("Final", "11 Mar 2014", "'it is the undertaking who needs to decide on the appropriate reference date for "
                                       "its ORSA'"),
        "3261": ("Final", "18 Feb 2025", "the ORSA supervisory report presents the results of the assessment of Art. 45 "
                                         "(its content, not who makes it)"),
        "460": ("Final", "08 Dec 2015", "a holding company's notional SCR in the group calculation (Art. 372 — not the ORSA)"),
    },
}
_BASIS = {"group": "Delegated Regulation (EU) 2015/35 Art. 372(1) (the group's ORSA supervisory report)",
          "undertaking": "Delegated Regulation (EU) 2015/35 Art. 304(1)(c) (the undertaking's ORSA supervisory report)"}
BASIS = {FRAMEWORK: {
    "who": "each insurance undertaking for itself, or a group",
    "title": "Who reports the ORSA",
    "shows": "Each undertaking reports its own assessment; a group reports the group's. An undertaking at the head of a group "
             "reports both: its own on its own business, and the group's. The whole organisation's book counts every entity "
             "in full, so it is neither.",
    "legal": "Directive 2009/138/EC, Art. 45(1), Art. 45(5) and Art. 246(1) and (4) (as amended by Directive (EU) 2025/2); "
             "Delegated Regulation (EU) 2015/35, Art. 304(1)(c), Art. 312(1)(b), Art. 372(1) and Art. 373.",
    "organisation": _BASIS["undertaking"]}}
NO_CHOICE = "a group or an undertaking of the entity structure"
# a filing's deadline runs from the assessment's conclusion (Art. 312(1)(b)); the calendar has no date of its own for it
DUE_RULE = "within 2 weeks after concluding the assessment (Art. 312(1)(b) Del. Reg. 2015/35)"


def choices(session: Session, org_id: str, framework: str, period_end: date) -> list[dict]:
    """Each group, then each entity that files its own report — the undertakings and groups of sii_filers, with the role
    each report takes: an undertaking at the head of a group appears twice, for the group ('consolidated') and for itself
    ('solo', its own book)."""
    from services.governance import sii_filers
    return sii_filers.choices(session, org_id)


def owed(session: Session, org_id: str, framework: str, period_end: date) -> set[tuple[str, str]]:
    """The ORSAs owed for a period, as (entity_id, role): every filer's, once a year (Art. 45(5) as replaced)."""
    return {(c["entity_id"], c["role"]) for c in choices(session, org_id, framework, period_end)}


def record(session: Session, org_id: str, framework: str, entity_id: str, group: bool, period_end: date | None) -> dict:
    from services.governance import report_filers as RF
    name = next((e["name"] for e in RF.entities(session, org_id) if e["entity_id"] == entity_id), None)
    level = "group" if group else "undertaking"
    return {"level": level, "entity_id": entity_id, "name": name, "basis": _BASIS[level]}
