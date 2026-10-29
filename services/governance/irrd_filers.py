"""Who draws up the pre-emptive recovery plan (insurer_recovery_stress) — the filer rule of
services.governance.report_filers for an organisation that records its undertakings as reporting entities, as Directive (EU) 2025/1 (the
IRRD, held in data/sources/legal) says:
- a group's plan is the ultimate parent's: "the group supervisor has the power to require that the ultimate parent
  undertaking of a group draw up and submit to the group supervisor a group pre-emptive recovery plan", which "shall
  consist of a pre-emptive recovery plan for the group headed by the ultimate parent undertaking" (Art. 7(1)) — each
  group here (a top entity with entities below it), on the group's figures;
- an undertaking outside such a group draws up its own: "insurance and reinsurance undertakings that are not part of a
  group subject to pre-emptive recovery planning pursuant to Article 7 ... draw up and keep updated a pre-emptive recovery
  plan" (Art. 5(1)) — a top entity with nothing below it;
- a subsidiary only where its supervisor requires it: "where no group pre-emptive recovery plan exists" (Art. 7(4)), or
  where the group plan does not sufficiently consider it (Art. 7(5)).
Whether an undertaking or a group is subject to planning at all is the supervisor's decision on the criteria of Art.
5(2) and (3) (at least 60 % of each market); the platform records no such decision, so it offers each filer the plan
and owes none on the calendar (the plan is updated at least every two years and after a material change, Art. 5(4) —
no calendar date). The filers offered are those of the Solvency II reports (services.governance.sii_filers: each group,
and each entity that files its own report), each frozen book recording which plan it is.

EIOPA Q&A on regulation (checked 2026-10-29: keywords 'pre-emptive' — none; 'recovery' — 9, none on Directive (EU)
2025/1): no answer on who draws up a pre-emptive recovery plan in a group.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

FRAMEWORK = "insurer_recovery_stress"
IRRD = "32025L0001"
QUOTES = {
    "IRRD Art. 5(1)": (IRRD, "Member States shall ensure that insurance and reinsurance undertakings that are not part of a "
                             "group subject to pre-emptive recovery planning pursuant to Article 7, and that meet the "
                             "criteria laid down in paragraph 2 or 3 of this Article, draw up and keep updated a "
                             "pre-emptive recovery plan."),
    "IRRD Art. 5(2)": (IRRD, "Member States shall ensure that the supervisory authority subjects insurance and reinsurance "
                             "undertakings to pre-emptive recovery planning requirements"),
    "IRRD Art. 7(1), first subparagraph": (IRRD, "Member States shall ensure that the group supervisor has the power to "
                                                 "require that the ultimate parent undertaking of a group draw up and submit "
                                                 "to the group supervisor a group pre-emptive recovery plan."),
    "IRRD Art. 7(1), second sentence": (IRRD, "Group pre-emptive recovery plans shall consist of a pre-emptive recovery plan "
                                              "for the group headed by the ultimate parent undertaking."),
    "IRRD Art. 7(4)": (IRRD, "Supervisory authorities may require subsidiary insurance or reinsurance undertakings or the "
                             "entities referred to in Article 1(1), points (c) and (d), to draw up and submit pre-emptive "
                             "recovery plans where no group pre-emptive recovery plan exists."),
    "IRRD Art. 2(70)": (IRRD, "‘ultimate parent undertaking’ means a parent undertaking in a Member State, of a group which "
                              "is subject to group supervision in accordance with Article 213(2), point (a) or (b), of "
                              "Directive 2009/138/EC"),
}
_BASIS = {"group": "Directive (EU) 2025/1 Art. 7(1) (the group's plan, by its ultimate parent undertaking)",
          "undertaking": "Directive (EU) 2025/1 Art. 5(1) (the undertaking's own plan)",
          "subsidiary_on_request": "Directive (EU) 2025/1 Art. 7(4), (5) (a subsidiary's own plan, where its supervisor "
                                   "requires it)"}
BASIS = {FRAMEWORK: {
    "who": "the ultimate parent for its group, or an undertaking outside a group plan",
    "title": "Who draws up the recovery plan",
    "shows": "A group's plan is drawn up by its ultimate parent; an undertaking outside a group plan draws up its own, and a "
             "subsidiary its own where its supervisor requires it. The whole organisation's book counts every entity in "
             "full, so it is neither.",
    "legal": "Directive (EU) 2025/1, Art. 5(1)-(3) and Art. 7(1), (4), (5).",
    "organisation": _BASIS["undertaking"]}}
NO_CHOICE = "a group or an undertaking of the entity structure"


def choices(session: Session, org_id: str, framework: str, period_end: date) -> list[dict]:
    """Each group, then each entity that files its own report — the groups and undertakings of sii_filers, one scope
    per entity: the ultimate parent's plan is the group's, its own remedial actions in it (Art. 7(1))."""
    from services.governance import sii_filers
    seen: set[str] = set()
    return [c for c in sii_filers.choices(session, org_id) if not (c["entity_id"] in seen or seen.add(c["entity_id"]))]


def owed(session: Session, org_id: str, framework: str, period_end: date) -> dict[str, str]:
    """Nothing by period: the supervisor decides who plans (Art. 5(2), 7(1)) and the plan has no calendar date."""
    return {}


def record(session: Session, org_id: str, framework: str, entity_id: str, group: bool, period_end: date | None) -> dict:
    """The plan a frozen book is for: the group's (a top entity with entities below it), an undertaking's own (a top
    entity alone), or a subsidiary's — owed only where its supervisor requires it."""
    from services.governance import report_filers as RF
    e = next(x for x in RF.entities(session, org_id) if x["entity_id"] == entity_id)
    level = ("group" if e["has_children"] else "undertaking") if e["parent_entity_id"] is None else "subsidiary_on_request"
    return {"level": level, "entity_id": entity_id, "name": e["name"], "basis": _BASIS[level]}
