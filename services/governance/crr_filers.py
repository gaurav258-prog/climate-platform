"""Who discloses ESG risks under Pillar 3 (bank_p3esg), and how often, as Regulation (EU) No 575/2013 (CRR) says — the
filer rule of services.governance.report_filers for an organisation that records its undertakings as reporting entities.

Part Eight applies to each institution on an individual basis (Art. 6(1)), but "No institution which is either a parent
undertaking or a subsidiary, and no institution included in the consolidation pursuant to Article 18, shall be required
to comply with the obligations laid down in Part Eight on an individual basis" (Art. 6(3)). Instead:
- "EU parent institutions shall comply with Part Eight on the basis of their consolidated situation" (Art. 13(1), first
  subparagraph): each group — a top entity with entities below it — files on its consolidated situation;
- "Large subsidiaries of EU parent institutions shall disclose the information specified in Articles ... 449a ... on an
  individual basis or, where applicable ..., on a sub-consolidated basis" (Art. 13(1), second subparagraph): a
  subsidiary files its own when it is stated to be a large institution (Art. 4(1)(146), (147)) for the reference date;
  a subsidiary with entities below it files on its sub-consolidated situation;
- an entity that is neither parent nor subsidiary (a top with nothing below it) is an institution on its own and files
  its own (Art. 6(1)). A branch is part of an undertaking, never a filer.

How often each filer discloses follows from its own size class and listing (services.governance.crr_frequency, E354):
twice a year — at the half-year and the year end — for a G-SII or a listed large institution, else once. Both are the
organisation's statements per institution and reference date (the bank_p3esg catalog: `large_institution` — a G-SII, a
large institution other than a G-SII, or not large — and `listed_institution`; a choice each, four eyes), one mechanism
for every institution of the structure: a group's EU parent and an institution on its own state theirs as a subsidiary
does. They are entered on the filing form ('Size class and listing') or, before a half-year's report exists, on the
reporting cockpit ('Who reports it').

EBA Single Rulebook Q&A (checked 2026-10-29; keyword 449a, 49 Q&As): 2022_6652 (final, submitted 7 Dec 2022, published
10 Mar 2023) and 2023_6708 (final, submitted 30 Jan 2023, published 25 Aug 2023): institutions disclose "at the highest
level of consolidation in the EU, as regulated in Article 13 CRR", for "the undertakings included in the scope of
prudential consolidation (based on Art. 18 CRR)"; 2023_6695 (final, published 25 Aug 2023) the same. These predate
Regulation (EU) 2024/1623, which added Article 449a to the large subsidiaries' list of Art. 13(1) (consolidated text of
1 January 2025, held); no Q&A on large subsidiaries since (re-checked 2026-10-31). Not modelled: an EU parent included in
a third-country parent's equivalent disclosures (Art. 13(3)), and an entity's authorisation — each entity of the tree that
is not a branch is read as an institution.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from services.governance import crr_frequency as CF

FRAMEWORK = "bank_p3esg"
CRR = "02013R0575-20250101"
KEY = "large_institution"                       # the size class, per institution (services.governance.datapoint_catalog)
LISTED_KEY = "listed_institution"               # the listing, per institution
CHOICES = {CF.GSII: "A G-SII", CF.LARGE: "A large institution, not a G-SII", CF.NOT_LARGE: "Not a large institution"}
LISTINGS = {CF.LISTED: "Listed", CF.NON_LISTED: "Not listed"}
LARGE_SIZES = {CF.GSII, CF.LARGE}
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
             "full, so it is none of these. A G-SII or a listed large institution discloses twice a year, at the half-year "
             "and the year end; every other institution once a year.",
    "legal": "Regulation (EU) No 575/2013, Art. 6(1) and (3), Art. 13(1), Arts 433a, 433b and 433c; EBA Q&A 2022_6652 and "
             "2023_6708.",
    "organisation": _BASIS["institution"]}}
NO_CHOICE = "a group or an institution of the entity structure"


def institutions(ents: list[dict]) -> list[dict]:
    """The entities a statement is made for: every entity of the structure that is not a branch."""
    from services.governance.report_filers import is_branch
    return [e for e in ents if not is_branch(e)]


def subsidiaries(ents: list[dict]) -> list[dict]:
    """The institutions below a parent in the tree."""
    return [e for e in institutions(ents) if e["parent_entity_id"] is not None]


def stated(session: Session, org_id: str, period_end: date) -> dict[str, dict]:
    """The attested statements for a reference date, {entity_id: {size, size_by, listing, listing_by}}."""
    from services.governance.provided_data import attested_values
    out: dict[str, dict] = {}
    for v in attested_values(session, org_id, FRAMEWORK, period_end):
        if v.get("member") and v["concept"] in (KEY, LISTED_KEY):
            k = "size" if v["concept"] == KEY else "listing"
            out.setdefault(v["member"], {}).setdefault(k, v["value"])          # newest first: the first one stands
            out[v["member"]].setdefault(f"{k}_by", v.get("attested_by"))
    return out


def frequency_of(st: dict, entity_id: str) -> dict:
    s = st.get(entity_id) or {}
    return CF.frequency(s.get("size"), s.get("listing"))


def _filers(ents: list[dict], st: dict) -> list[dict]:
    """Each group, each institution on its own, then each subsidiary stated large — with its filing's role."""
    from services.governance import report_filers as RF
    alone = [{"entity_id": e["entity_id"], "name": e["name"], "role": "solo"} for e in institutions(ents)
             if e["parent_entity_id"] is None and not e["has_children"]]
    subs = [{"entity_id": e["entity_id"], "name": e["name"], "role": "consolidated" if e["has_children"] else "solo"}
            for e in subsidiaries(ents) if (st.get(e["entity_id"]) or {}).get("size") in LARGE_SIZES]
    return RF.groups(ents) + alone + subs


def choices(session: Session, org_id: str, framework: str, period_end: date, half_year: bool = False) -> list[dict]:
    """The filers for a reference date; for a half-year, only those that disclose twice a year."""
    from services.governance import report_filers as RF
    st = stated(session, org_id, period_end)
    out = _filers(RF.entities(session, org_id), st)
    if half_year:
        out = [c for c in out if frequency_of(st, c["entity_id"])["frequency"] == CF.SEMIANNUAL]
    return out


def owed(session: Session, org_id: str, framework: str, period_end: date, half_year: bool = False) -> dict[str, str]:
    return {c["entity_id"]: c["role"] for c in choices(session, org_id, framework, period_end, half_year)}


def undetermined(session: Session, org_id: str, period_end: date, half_year: bool) -> list[dict]:
    """The institutions whose part in the report for this reference date is not known yet, [{entity_id, name, needs,
    msg}]: for a year end, a subsidiary whose size class is not stated (a large one files its own); for a half-year,
    every possible filer whose size class or listing is not stated (it files at the half-year only if it discloses twice
    a year)."""
    from core import messages
    from services.governance import report_filers as RF
    ents = RF.entities(session, org_id)
    st = stated(session, org_id, period_end)
    out = []
    if RF.is_filer(session, org_id):           # the organisation is the institution: it states its own, keyed by itself
        needs = frequency_of(st, org_id)["needs"] if half_year else []
        out = [{"entity_id": None, "name": _org_name(session, org_id), "needs": needs}] if needs else []
    elif half_year:
        # a subsidiary whose size class is not stated may be large, and then a filer
        unsized = {e["entity_id"] for e in subsidiaries(ents) if not (st.get(e["entity_id"]) or {}).get("size")}
        for c in _filers(ents, {**st, **{m: {**st.get(m, {}), "size": CF.LARGE} for m in unsized}}):
            needs = frequency_of(st, c["entity_id"])["needs"]
            if needs:
                out.append({"entity_id": c["entity_id"], "name": c["name"], "needs": needs})
    else:
        out = [{"entity_id": e["entity_id"], "name": e["name"], "needs": ["size"]} for e in subsidiaries(ents)
               if not (st.get(e["entity_id"]) or {}).get("size")]
    code = "filing.to_state.esg_half_year" if half_year else "filing.to_state.esg_size"
    for u in out:
        u["member"] = u["entity_id"] or org_id
        u["msg"] = messages.render(code, name=u["name"], date=period_end.isoformat())
        u["statements"] = [STATEMENTS[n] for n in u["needs"]]
    return out


# what the cockpit asks for each statement still to make (screen words; the citations are in the catalog's note)
STATEMENTS = {"size": {"key": KEY, "label": "Size class", "choices": CHOICES, "listing_for": [CF.LARGE]},
              "listing": {"key": LISTED_KEY, "label": "Listing", "choices": LISTINGS}}


def _org_name(session: Session, org_id: str) -> str:
    from sqlalchemy import text
    return session.execute(text("SELECT name FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": org_id}).scalar() or "—"


def organisation_record(session: Session, org_id: str, period_end: date | None, half_year: bool = False) -> dict:
    """The organisation's own filer record while it is the institution (it records no entity): its statements are keyed
    by the organisation itself."""
    st = stated(session, org_id, period_end) if period_end else {}
    me = _row({"entity_id": org_id, "name": _org_name(session, org_id)}, st)
    return {"level": "organisation", "entity_id": None, "basis": _BASIS["institution"], "half_year": half_year,
            "frequency": me["frequency"], "frequency_basis": me["frequency_basis"], "self": me}


def _row(e: dict, st: dict) -> dict:
    s, f = st.get(e["entity_id"]) or {}, frequency_of(st, e["entity_id"])
    return {"entity_id": e["entity_id"], "name": e["name"], "stated": s.get("size"), "attested_by": s.get("size_by"),
            "listing": s.get("listing"), "listing_by": s.get("listing_by"), "frequency": f["frequency"],
            "frequency_basis": f["basis"]}


def record(session: Session, org_id: str, framework: str, entity_id: str, group: bool, period_end: date | None,
           half_year: bool = False) -> dict:
    """The filer an entity's book is for, with how often it discloses; a group's record lists its subsidiaries with their
    stated size class and listing (the form section where they are stated)."""
    from services.governance import entities as E
    from services.governance import report_filers as RF
    ents = {e["entity_id"]: e for e in RF.entities(session, org_id)}
    e = ents[entity_id]
    st = stated(session, org_id, period_end) if period_end else {}
    if e["parent_entity_id"] is None:
        level = "group" if e["has_children"] else "institution"
    else:
        level = "large_subsidiary" if (st.get(entity_id) or {}).get("size") in LARGE_SIZES else "not_owed"
    me = _row(e, st)
    out = {"level": level, "entity_id": entity_id, "name": e["name"], "basis": _BASIS[level], "half_year": half_year,
           "frequency": me["frequency"], "frequency_basis": me["frequency_basis"], "self": me}
    if level == "large_subsidiary" and group:
        out["basis"] += " (on its sub-consolidated situation)"
    if level == "group":
        tree = set(E.subtree_ids(session, org_id, entity_id))
        out["subsidiaries"] = [_row(s, st) for s in subsidiaries(list(ents.values())) if s["entity_id"] in tree]
    return out


def half_year_refusal(session: Session, org_id: str, entity_id: str | None, period_end: date) -> tuple[str, dict] | None:
    """(catalogue code, params) when the scope discloses no half-year report for this reference date, else None."""
    from services.governance import report_filers as RF
    if entity_id is None:
        if not RF.is_filer(session, org_id):
            return None                         # the whole-organisation refusal answers first (no filer's book)
        member, name = org_id, _org_name(session, org_id)
    else:
        member = entity_id
        name = next((e["name"] for e in RF.entities(session, org_id) if e["entity_id"] == entity_id), "—")
    f = frequency_of(stated(session, org_id, period_end), member)
    if f["frequency"] == CF.SEMIANNUAL:
        return None
    if f["frequency"] is None:
        return "filing.refused.esg_frequency_unstated", {"name": name, "date": period_end.isoformat()}
    return "filing.refused.esg_annual_filer", {"name": name, "why": f["basis"]}


def check_member(session: Session, org_id: str, member: str | None) -> None:
    """A statement names one of the organisation's institutions (an entity of the structure, not a branch) — or, while it
    records no entity, the organisation itself; ValueError else."""
    from services.governance import report_filers as RF
    own = {org_id} if RF.is_filer(session, org_id) else set()
    if member not in own | {e["entity_id"] for e in institutions(RF.entities(session, org_id))}:
        raise ValueError("not an institution of the organisation's entity structure")


def _cells(r: dict) -> list[dict]:
    m = r["entity_id"]
    return [{"text": r["name"]},
            {"text": CHOICES.get(r.get("stated"), "—"), "key": f"{KEY}@{m}", "frozen_value": r.get("stated"),
             "supply": {"framework": FRAMEWORK, "key": KEY, "member": m, "choices": CHOICES}},
            {"text": LISTINGS.get(r.get("listing"), "—"), "key": f"{LISTED_KEY}@{m}", "frozen_value": r.get("listing"),
             "supply": {"framework": FRAMEWORK, "key": LISTED_KEY, "member": m, "choices": LISTINGS}},
            {"text": CF.WORDS.get(r.get("frequency"), "To state") if "frequency" in r else "—"},   # "—": frozen before E354
            {"text": ", ".join(sorted({x for x in (r.get("attested_by"), r.get("listing_by")) if x})) or "—"}]


def statement_section(payload: dict | None) -> dict | None:
    """The filing's 'Size class and listing': the filer's own row, and a group's subsidiaries, each with the size class
    and listing frozen with it and an entry for the reference date's statement (a choice, attested by a second person) —
    which decide how often the filer discloses and which subsidiaries disclose their own."""
    f = (payload or {}).get("_filer") or {}
    if f.get("level") not in ("group", "institution", "large_subsidiary", "organisation"):
        return None
    subs = f.get("subsidiaries") or []
    shown = ([f["self"]] if f.get("self") else []) + subs        # a record frozen before E354 holds no row of its own
    if not shown:
        return None
    rows = [{"type": "row", "cells": _cells(r)} for r in shown]
    unstated = [r["name"] for r in shown if "frequency" in r and r["frequency"] is None]
    note = ("A G-SII or a listed large institution discloses at the half-year and the year end; every other institution at "
            "the year end. A large subsidiary discloses its own. The calendar follows each statement once a second person "
            "approves it." + (f" Not stated: {', '.join(unstated)}." if unstated else ""))
    return {"title": "Size class and listing", "key": KEY,
            "columns": ["Institution", "Size class", "Listing", "Discloses", "Attested by"],
            "col_sources": ["", "manual", "manual", "", ""], "rows": rows, "note": note}


def _day(d: str) -> str:
    x = date.fromisoformat(d)
    return f"{x.day} {x:%B %Y}"


def period_section(payload: dict | None) -> dict | None:
    """The filing's 'Disclosure period': its reference date, the period it covers and how often its filer discloses —
    the disclosure reference date and reference period Implementing Regulation (EU) 2024/3172 Art. 25(5)(a) asks for.
    From the period frozen with the book (`_period`, E354); none for a filing frozen before it was kept."""
    p = (payload or {}).get("_period")
    if not p:
        return None
    f = (payload or {}).get("_filer") or {}
    rows = [["Disclosure reference date", _day(p["end"])],
            ["Reference period", f"{_day(p['start'])} to {_day(p['end'])} · {p['words']}"]]
    if f.get("frequency") in CF.WORDS:
        rows.append(["How often it discloses", CF.WORDS[f["frequency"]]])
    return {"title": "Disclosure period", "key": "period", "columns": ["", ""],
            "rows": [{"type": "row", "cells": [{"text": a}, {"text": b}]} for a, b in rows]}
