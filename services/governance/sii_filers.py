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

The two duties have different subjects and stand side by side. Art. 19(1) binds every insurance and reinsurance
undertaking ("Insurance and reinsurance undertakings ... shall submit annually"), the regular reporting of Del. Reg.
Art. 304(1); Art. 34(1) binds the participating undertaking for its group. So an insurance undertaking at the head of a
group owes both: its own S.27.01.01 on its own book, and the group's S.27.01.04 — two reports of one entity, told apart by
their role ('solo' = its own book, entities.own_book_ids; 'consolidated' = the group's). Its own book is its business —
"all business", a contract "sold through a branch" included (Annex II S.04.03) — never an undertaking below it. The two
are due apart: an undertaking's annual templates "no later than 14 weeks after the undertaking's financial year end"
(Del. Reg. Art. 312(1)(c)), the group's 6 weeks later (Art. 373 applies Art. 312 to the group's reporting, "extended by
6 weeks").

Who owes what, from the entity structure the organisation states:
- the organisation as a whole is the undertaking only while it records none: once an undertaking is recorded as a
  reporting entity, that entity reports for itself, and the whole organisation is no second filer of the same report —
  as for CSRD, where the undertakings are "each reporting entity; the organisation itself when it has none"
  (services.governance.csrd_scope.undertakings). An organisation of one recorded undertaking owes that undertaking's one
  S.27.01.01, not a whole-organisation copy of it;
- a group: each top entity with an undertaking below it (a branch is part of its undertaking, not one below it);
- an undertaking for itself: each entity set to file its own report (requires_solo_filing) that is not a group node;
- a lower group node (kind group / sub_group) set to file: its sub-group's consolidated report — sub-group supervision is
  "a decision made by the relevant NCAs" (EIOPA Q&A 2109), which the node records.
A node of kind group or sub_group (entities.GROUP_KINDS) stands for the group, not for an undertaking: it owes no report
for itself. The whole-organisation scope of an organisation that records an undertaking is refused with the filers to
choose from. Each freeze records its filer (`_filer`); a whole-organisation filing without that record exports no template.

EIOPA Q&A on regulation (QA): none says a participating undertaking's own templates give way to the group's, or that
one undertaking submits two S.27.01.01 for one year; the answers read the participating undertaking's own (solo) level
beside the group's.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

FRAMEWORK = "insurer_solvency"
ITS, DR = "32023R0894", "02015R0035-20241114"
# each reading above, in the act's own words (data/sources/legal; checked word for word by tests/unit/test_sii_filers.py)
QUOTES = {
    "ITS Art. 19(1)": (ITS, "Insurance and reinsurance undertakings and captive insurance undertakings shall submit annually "
                            "the information referred to in Article 304(1), point (d), of Delegated Regulation (EU) 2015/35"),
    "ITS Art. 19(1)(s)(i)": (ITS, "for insurance and reinsurance undertakings other than captive insurance or captive "
                                  "reinsurance undertaking, template S. 27.01.01 of Annex I"),
    "ITS Annex II S.01.02 C0010/R0020": (ITS, "Identification code of the undertaking, using the Legal Entity Identifier (LEI)"),
    "ITS Annex II S.04.03": (ITS, "This section relates to annual submission of information for individual insurance and "
                                  "reinsurance undertakings only"),
    "ITS Annex II S.04.03, all business": (ITS, "entities shall report all business"),
    "ITS Annex II S.04.03, branches": (ITS, "The country where the branch is located (host country) when the contract was "
                                           "sold through a branch"),
    "ITS Art. 34(1)": (ITS, "Participating insurance and reinsurance undertakings, insurance holding companies and mixed "
                            "financial holding companies which, for the calculation of group solvency, use the method 1 as "
                            "defined in Article 230 of Directive 2009/138/EC"),
    "ITS Art. 34(1)(s)": (ITS, "template S.27.01.04 of Annex I, specifying information on non-life catastrophe risk"),
    "ITS Annex III S.01.02 C0010/R0010": (ITS, "Legal name of the participating insurance and reinsurance undertaking or "
                                               "insurance holding company or mixed financial holding company at the head of "
                                               "the insurance or reinsurance group"),
    "ITS Annex III S.01.02 C0010/R0020": (ITS, "Identification code of the participating undertaking, using the Legal Entity "
                                               "Identifier (‘LEI’)"),
    "Del. Reg. Art. 304(1)": (DR, "The information which supervisory authorities require insurance and reinsurance undertakings "
                                  "to submit at predefined periods in accordance with Article 35(2)(a)(i) of Directive 2009/138/EC"),
    "Del. Reg. Art. 372(1)": (DR, "participating insurance and reinsurance undertakings, insurance holding companies or mixed "
                                  "financial holding companies shall be required to submit to the group supervisor"),
    "Del. Reg. Art. 312(1)(c)": (DR, "the annual quantitative templates referred to in Article 304(1)(d) of this Regulation "
                                     "within the deadlines set out in article 308b(5) of Directive 2009/138/EC and, after the end "
                                     "of the transitional period set out in that Article, no later than 14 weeks after the "
                                     "undertaking's financial year end"),
    "Del. Reg. Art. 373": (DR, "Article 312 of this Regulation shall apply to the submission by participating insurance and "
                               "reinsurance undertakings, insurance holding companies or mixed financial holding companies of "
                               "their group regular supervisory reporting"),
    "Del. Reg. Art. 373, 6 weeks": (DR, "For the purposes of this Article the deadlines referred to in Article 312 shall be "
                                        "extended by 6 weeks, except for the ORSA supervisory report"),
}
# a group's report is due 6 weeks after an undertaking's (Del. Reg. Art. 373 on Art. 312(1)(c)'s 14 weeks)
GROUP_EXTRA_WEEKS = 6
GROUP_DUE_RULE = "20 weeks after financial year end (Art. 312(1)(c) with Art. 373 Del. Reg. 2015/35)"
# EIOPA Q&A on regulation read for this reading (search-qas_en: templates S.01.01, S.01.02, S.27.01; topic group solvency
# requirement; keywords "participating undertaking", "solo and group"), each with its status and date of submission
QA = {
    "checked": ["2026-10-23", "2026-10-25", "2026-10-29"],
    "read": {
        "1718": ("Final", "14 Nov 2018", "the participating insurance undertaking's basic own funds 'on the solo level' — its "
                                         "own returns beside its subsidiary's"),
        "2733": ("Final", "06 Jul 2023", "'the SCRs at individual entity level of the participating undertaking and each "
                                         "related insurance or reinsurance undertaking'"),
        "2097": ("Final", "07 Jan 2020", "a parent undertaking 'obligated to provide both solo reporting and group reporting': "
                                         "a subsidiary one row in its solo S.06.02.01, consolidated in the group's"),
        "1011": ("Final", "16 Dec 2016", "a group member is relieved of a solo template only where the ITS says so (S.36, "
                                         "intra-group transactions); Art. 19(1)(s) says no such thing of S.27.01"),
        "2848": ("Revised", "31 Oct 2023", "S.36 is an individual undertaking's template where both conditions of the ITS "
                                           "hold: which solo templates an undertaking in a group reports is the ITS's to say"),
        "2109": ("Final", "11 Feb 2020", "sub-group supervision is 'a decision made by the relevant NCAs' (Del. Reg. Art. 358)"),
    },
}
UNDERTAKING = {"template": "S.27.01.01", "basis": "Implementing Regulation (EU) 2023/894 Art. 19(1)(s)(i)"}
GROUP = {"template": "S.27.01.04", "basis": "Implementing Regulation (EU) 2023/894 Art. 34(1)(s)"}


def _kind(e: dict) -> str:
    return (e.get("kind") or "").strip().lower()


def _entities(session: Session, org_id: str) -> list[dict]:
    """The organisation's reporting entities, each with whether an undertaking stands below it (any depth; a branch is
    part of its undertaking, never one below it)."""
    from services.governance.entities import GROUP_KINDS
    ents = [dict(r) for r in session.execute(text("""
        SELECT e.entity_id::text AS entity_id, e.name, e.kind, e.parent_entity_id::text AS parent_entity_id,
               e.requires_solo_filing
        FROM reporting_entities e WHERE e.org_id = :o ORDER BY e.name, e.entity_id"""), {"o": org_id}).mappings()]
    kids: dict[str | None, list[dict]] = {}
    for e in ents:
        kids.setdefault(e["parent_entity_id"], []).append(e)

    def below(eid: str, seen: frozenset = frozenset()) -> bool:
        return any(_kind(c) != "branch" or below(c["entity_id"], seen | {eid})
                   for c in kids.get(eid, []) if c["entity_id"] not in seen)
    for e in ents:
        e["undertaking_below"] = below(e["entity_id"])
        e["undertaking"] = _kind(e) not in GROUP_KINDS | {"branch"}
        e["group_node"] = _kind(e) in GROUP_KINDS
    return ents


def is_filer(session: Session, org_id: str) -> bool:
    """Whether the organisation as a whole is a filer: it is the undertaking while it records none of its own."""
    return not any(e["undertaking"] for e in _entities(session, org_id))


def choices(session: Session, org_id: str) -> list[dict]:
    """The filers a preparer chooses from, with the role each report takes: each group (a top entity with an undertaking
    below it; 'consolidated'), then each entity that files its own report — an undertaking for itself ('solo', its own
    book), a lower group node for its sub-group ('consolidated'). One entity may appear twice: an undertaking at the head
    of a group reports for the group and for itself."""
    ents = _entities(session, org_id)
    groups = [{"entity_id": e["entity_id"], "name": e["name"], "role": "consolidated"}
              for e in ents if e["parent_entity_id"] is None and e["undertaking_below"]]
    own = [{"entity_id": e["entity_id"], "name": e["name"], "role": "consolidated" if e["group_node"] else "solo"}
           for e in ents if e["requires_solo_filing"]
           and (not e["group_node"] or (e["parent_entity_id"] is not None and e["undertaking_below"]))]
    return groups + own


def choice_label(c: dict) -> str:
    return f"{c['name']} (group)" if c["role"] == "consolidated" else c["name"]


def whole_org_refusal(session: Session, org_id: str, framework: str, entity_id: str | None) -> tuple[str, dict] | None:
    """(catalogue code, params) when a whole-organisation scope is not a filer's for this report, else None."""
    if framework != FRAMEWORK or entity_id is not None or is_filer(session, org_id):
        return None
    return "filing.refused.sii_whole_org", {"choices": ", ".join(choice_label(c) for c in choices(session, org_id)) or "—"}


def owed(session: Session, org_id: str) -> set[tuple[str | None, str]]:
    """The reports the calendar owes for a period, as (entity_id — None = the organisation, filing role)."""
    out = {(c["entity_id"], c["role"]) for c in choices(session, org_id)}
    return out | {(None, "whole_org")} if is_filer(session, org_id) else out


def due(undertaking_due, role: str):
    """The deadline of a report: an undertaking's (the calendar's rule, Art. 312(1)(c)), a group's 6 weeks later."""
    from datetime import timedelta
    return undertaking_due + timedelta(weeks=GROUP_EXTRA_WEEKS) if role == "consolidated" and undertaking_due else undertaking_due


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
    filing frozen without its filer record (before it was kept, or when the organisation records its undertakings) —
    else None. Its template (XBRL, workbook) is not produced."""
    if role == "whole_org" and unrecorded_whole_org(payload):
        return "filing.refused.sii_whole_org_frozen", {}
    return None
