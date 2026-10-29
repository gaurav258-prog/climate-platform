"""Who reports the EU Taxonomy Article 8 KPIs (bank_tcfd, reit_taxonomy) — the filer rule of
services.governance.report_filers for an organisation of two or more reporting entities.

Delegated Regulation (EU) 2021/2178 names its reporters by the Accounting Directive: a 'financial undertaking' and a
'non-financial undertaking' are each "an undertaking that is subject to the disclosure obligations laid down in Articles
19a and 29a of Directive 2013/34/EU" (Art. 1(8), (9)). Each reports at its own level — a non-financial undertaking's KPIs
"at the level of the individual undertaking where that undertaking prepares only individual non-financial statements or
at the level of the group where the undertaking prepares consolidated non-financial statements" (Annex I, 1.2(f)); a
credit institution's (Art. 4(1)) "on the basis of the scope of their prudential consolidation" (Annex V, 1.1.1). A
subsidiary included in its parent's consolidated management report is exempted (Directive 2013/34/EU Art. 19a(9), 29a(8)
as replaced by Directive (EU) 2022/2464).

These are the undertakings of the ESRS statement, and the platform holds them once: each undertaking's reporting role for
the year (services.governance.csrd_roles — individual, consolidated, exempt subsidiary or voluntary; four eyes) and
whether Art. 5(2) of Directive (EU) 2022/2464 requires its statement on its stated facts (services.governance.csrd_scope).
A filer is an undertaking stated to report individually (Art. 19a) or for its group (Art. 29a); the calendar owes it
unless its stated facts show the Directive does not require its statement. An exempt subsidiary files none (refused); an
undertaking whose role is not stated is listed as still to be stated (services.governance.filings.undetermined_filers).

The regulator's answers (checked 2026-10-29): Commission Notice C/2023/305 (OJ C 305, 20 October 2023) FAQ 9 — KPIs at
the individual or the group level as Articles 19a and 29a decide; FAQ 11 — an undertaking exempt under those Articles is
"also exempted from making Taxonomy related disclosures under Article 8(1)", and the CSRD's exemptions in Art. 19a(9) and
29a(8) are "similar". EBA Q&A 2023_6695 (final, published 25 August 2023): the Taxonomy applies to the undertakings of
Article 19a or 29a, Pillar 3 ESG at the highest level of consolidation in the EU.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

FRAMEWORKS = ("bank_tcfd", "reit_taxonomy")
DR, CSRD = "02021R2178-20240101", "32022L2464"
QUOTES = {
    "Del. Reg. 2021/2178 Art. 1(8)": (DR, "‘financial undertaking’ means an undertaking that is subject to the disclosure "
                                          "obligations laid down in Articles 19a and 29a of Directive 2013/34/EU"),
    "Del. Reg. 2021/2178 Art. 1(9)": (DR, "‘non-financial undertaking’ means an undertaking that is subject to the "
                                          "disclosure obligations laid down in Articles 19a and 29a of Directive "
                                          "2013/34/EU and is not a financial undertaking"),
    "Del. Reg. 2021/2178 Art. 4(1)": (DR, "Credit institutions shall disclose the information referred to in Article 8(1) "
                                          "of Regulation (EU) 2020/852 as specified in Annexes V and XI to this Regulation."),
    "Del. Reg. 2021/2178 Annex V, 1.1.1": (DR, "Credit institutions shall disclose relevant KPIs on the basis of the scope "
                                               "of their prudential consolidation determined in accordance with Regulation "
                                               "(EU) No 575/2013, Title II, Chapter 2, Section 2."),
    "Del. Reg. 2021/2178 Annex I, 1.2(f)": (DR, "the KPIs shall be provided at the level of the individual undertaking where "
                                                "that undertaking prepares only individual non-financial statements or at "
                                                "the level of the group where the undertaking prepares consolidated "
                                                "non-financial statements"),
    "Directive 2013/34/EU Art. 19a(9)": (CSRD, "an undertaking which is a subsidiary undertaking shall be exempted from the "
                                               "obligations set out in paragraphs 1 to 4 of this Article (“the exempted "
                                               "subsidiary undertaking”) if such undertaking and its subsidiary "
                                               "undertakings are included in the consolidated management report of a "
                                               "parent undertaking"),
    "Directive 2013/34/EU Art. 29a(8)": (CSRD, "a parent undertaking which is a subsidiary undertaking shall be exempted "
                                               "from the obligations set out in paragraphs 1 to 5 of this Article"),
}
_BASIS = {"group": "Directive 2013/34/EU Art. 29a (Delegated Regulation (EU) 2021/2178 Art. 1(8), (9))",
          "undertaking": "Directive 2013/34/EU Art. 19a (Delegated Regulation (EU) 2021/2178 Art. 1(8), (9))",
          "not_owed": "Not stated to report under Article 19a or 29a of Directive 2013/34/EU for the year"}
_SHOWS = ("Each undertaking that reports under the Accounting Directive reports its KPIs — for itself, or for its group "
          "{group}; an exempt subsidiary is in its parent's report. The whole organisation's book counts every entity in "
          "full, so it is no undertaking's.")
BASIS = {
    "bank_tcfd": {"who": "each undertaking that reports for itself (Article 19a of Directive 2013/34/EU) or for its group "
                         "(Article 29a)",
                  "title": "Who reports the EU Taxonomy KPIs",
                  "shows": _SHOWS.format(group="on the scope of its prudential consolidation"),
                  "legal": "Delegated Regulation (EU) 2021/2178, Art. 1(8), Art. 4 and Annex V, 1.1.1; Directive "
                           "2013/34/EU, Arts 19a and 29a; Commission Notice C/2023/305, FAQ 9 and 11.",
                  "organisation": _BASIS["undertaking"]},
    "reit_taxonomy": {"who": "each undertaking that reports for itself (Article 19a of Directive 2013/34/EU) or for its "
                             "group (Article 29a)",
                      "title": "Who reports the EU Taxonomy KPIs",
                      "shows": _SHOWS.format(group="on its consolidated statements"),
                      "legal": "Delegated Regulation (EU) 2021/2178, Art. 1(9) and Annex I, 1.2(f); Directive 2013/34/EU, "
                               "Arts 19a and 29a; Commission Notice C/2023/305, FAQ 9 and 11.",
                      "organisation": _BASIS["undertaking"]},
}
NO_CHOICE = "none yet — state each undertaking's reporting role for the year"
FILES = ("individual", "consolidated")


def undertakings(session: Session, org_id: str, period_end: date) -> list[dict]:
    """Every undertaking with its stated role and requirement for the year (services.governance.csrd_scope) — the one
    list the ESRS statement's calendar and these reports read."""
    from services.calc_settings import get_calc_settings
    from services.governance import csrd_scope
    return csrd_scope.undertakings(session, org_id, period_end, get_calc_settings(session, org_id))


def _role(u: dict) -> str:
    return "consolidated" if u["role"] == "consolidated" else "solo"


def choices(session: Session, org_id: str, framework: str, period_end: date) -> list[dict]:
    """Each undertaking stated to report for itself or for its group, with its filing's role."""
    return [{"entity_id": u["entity_id"], "name": u["name"], "role": _role(u)}
            for u in undertakings(session, org_id, period_end) if u["role"] in FILES and u["entity_id"] is not None]


def owed(session: Session, org_id: str, framework: str, period_end: date) -> dict[str, str]:
    """Those the calendar owes: a filer whose stated facts do not show the Directive leaves its statement unrequired."""
    return {u["entity_id"]: _role(u) for u in undertakings(session, org_id, period_end)
            if u["role"] in FILES and u["entity_id"] is not None and u["required"] is not False}


def undetermined(session: Session, org_id: str, period_end: date) -> list[dict]:
    """The undertakings whose reporting role for the year is not stated — not branches — with what is missing."""
    from services.governance import report_filers as RF
    ents = {e["entity_id"]: e for e in RF.entities(session, org_id)}
    return [{"entity_id": u["entity_id"], "name": u["name"], "msg": u.get("msg")}
            for u in undertakings(session, org_id, period_end)
            if u["role"] is None and u["entity_id"] in ents and not RF.is_branch(ents[u["entity_id"]])]


def record(session: Session, org_id: str, framework: str, entity_id: str, group: bool, period_end: date | None) -> dict:
    from services.governance import report_filers as RF
    from services.governance.csrd_roles import live_role
    role = (live_role(session, org_id, entity_id, period_end) or {}).get("role") if period_end else None
    level = {"consolidated": "group", "individual": "undertaking"}.get(role, "not_owed")
    name = next((e["name"] for e in RF.entities(session, org_id) if e["entity_id"] == entity_id), None)
    return {"level": level, "entity_id": entity_id, "name": name, "basis": _BASIS[level]}


def exempt_refusal(session: Session, org_id: str, framework: str, entity_id: str | None,
                   period_end: date) -> tuple[str, dict] | None:
    """An exempt subsidiary reports no KPIs of its own: they are in its parent's consolidated report."""
    if framework not in FRAMEWORKS or entity_id is None:
        return None
    from services.governance.csrd_roles import live_role
    r = live_role(session, org_id, entity_id, period_end)
    if r and r["role"] == "exempt_subsidiary":
        return "filing.refused.exempt_subsidiary_taxonomy", {"parent": r.get("parent_name") or "—",
                                                             "report_ref": r.get("parent_report_ref") or "—"}
    return None
