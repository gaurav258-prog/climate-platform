"""CRCS · regulation version register (N-1 lifecycle).

For each framework a client files, this reconstructs the regulation's version lineage — the base act and the
amendments that have changed it — from the live EUR-Lex (Cellar) snapshots the detector already holds. It shows
which version is in force now, the effective-date milestones (past and upcoming), and whether an older basis is
being superseded. This is the "know exactly which version you're filing against, and what's coming" pillar of
the Continuous Regulatory Compliance System. Dates are live from the register; nothing is guessed.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

# each watched act's title and role: from its specification or data/reference/crcs/tracked_acts.json
from services.regulatory_monitoring.tracked_acts import act_meta  # noqa: E402


def _milestones(eif: list[str]) -> dict:
    today = date.today().isoformat()
    past = [d for d in eif if d <= today]
    future = [d for d in eif if d > today]
    return {"in_force_since": min(eif) if eif else None,
            "latest_effective": max(past) if past else None,
            "next_effective": min(future) if future else None,
            "future": future}


def versions(session: Session, org_type: str | None) -> dict:
    """Per applicable framework, the version lineage (base + amendments) with live effective-date milestones."""
    from sqlalchemy import text

    from services.governance.filings import FRAMEWORKS
    from services.governance.reg_reference import REFERENCE
    from services.regulatory_monitoring.eurlex_detector import FRAMEWORK_CELEX

    snaps = {r["celex"]: (r["signal"] or {}, r["checked_at"]) for r in
             session.execute(text("SELECT celex, signal, checked_at FROM reg_source_snapshot")).mappings()}

    # frameworks this sector files, plus EUDR for agri (filed via the disclosure page, not in FRAMEWORKS)
    applicable = [fw for fw, meta in FRAMEWORKS.items() if org_type in (meta.get("sectors") or ())]
    if org_type == "manufacturer" and "eudr_dds" not in applicable:
        applicable.append("eudr_dds")

    out = []
    for fw in applicable:
        meta = FRAMEWORKS.get(fw, {})
        acts = []
        checked = None
        for cx in FRAMEWORK_CELEX.get(fw, []):
            sig, ck = snaps.get(cx, ({}, None))
            eif = sig.get("entry_into_force") or []
            m = _milestones(eif)
            am = act_meta(cx)
            if ck:
                checked = ck.date().isoformat()
            rels = _relations(session, [cx])
            acts.append({
                "replaced_by": [{"celex": r["related_celex"], "title": short_title(r["title"], r["related_celex"]),
                                 "relation": r["relation"], "since": min(r["entry_into_force"]) if r["entry_into_force"] else None}
                                for r in rels if r["relation"] != "amends"],
                "amendments": sorted(({"celex": r["related_celex"], "title": short_title(r["title"], r["related_celex"]),
                                       "since": min(r["entry_into_force"]) if r["entry_into_force"] else None}
                                      for r in rels if r["relation"] == "amends"), key=lambda a: a["since"] or "", reverse=True),
                "ends": (sig.get("end_of_validity") if sig.get("end_of_validity") not in (None, _NO_END) else None),
                "celex": cx, "title": am["title"], "role": am["role"],
                "in_force": bool(sig.get("in_force")),
                "in_force_since": m["in_force_since"], "next_effective": m["next_effective"],
                "future": m["future"],
                "url": f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{cx}",
                "live": bool(sig),
            })
        if not acts:
            continue
        base = next((a for a in acts if a["role"] == "base"), acts[0])
        amendments = [a for a in acts if a["role"] == "amendment"]
        # the version "in force now" = base as amended; a pending future milestone means a new version is coming
        upcoming = sorted({d for a in acts for d in a["future"]})
        out.append({
            "framework": fw,
            "name": (REFERENCE.get(fw) or {}).get("official_name") or meta.get("label"),
            "authority": (REFERENCE.get(fw) or {}).get("authority") or meta.get("regulator"),
            "current_since": base["in_force_since"],
            "amended_by": len(amendments),
            "upcoming_effective": upcoming[0] if upcoming else None,
            "acts": acts,
            "checked_at": checked,
        })
    out.sort(key=lambda x: x["name"] or "")
    return {"frameworks": out, "checked_at": next((f["checked_at"] for f in out if f["checked_at"]), None),
            "summary": {"n": len(out), "n_upcoming": sum(1 for f in out if f["upcoming_effective"])}}


# ───────────────────────────── version pinning: which version a filing is prepared under ─────────────────────────────

LEGACY_SUPPORT_DAYS = 183     # CRCS policy: a version that has ended stays supported for restatements for six months
_NO_END = "9999-12-31"


def short_title(title: str | None, celex: str) -> str:
    """'Commission Implementing Regulation (EU) 2024/3172 of 29 November 2024 laying down …' → up to the act number."""
    import re
    m = re.match(r"^(.*?\((?:EU|EEC|EC|Euratom)\)\s*(?:No\s*)?\d+/\d+)", title or "")
    return m.group(1) if m else (title or celex)


def _relations(session: Session, celex_list: list[str]) -> list[dict]:
    """Acts that amend or replace these acts (live from the register), minus any a reviewer dismissed as immaterial."""
    from sqlalchemy import text
    rows = session.execute(text("""
        SELECT r.celex, r.related_celex, r.relation, r.title, r.entry_into_force, r.in_force
        FROM reg_act_relation r
        WHERE r.celex = ANY(:c) AND NOT EXISTS (
            SELECT 1 FROM reg_detected_change d WHERE d.celex = r.related_celex AND d.status = 'dismissed')
    """), {"c": celex_list}).mappings().all()
    return [dict(r) for r in rows]


def version_for(session: Session, framework: str, period_end: date | str, on: date | str | None = None) -> dict | None:
    """The regulation version a filing for `period_end` is prepared under, and whether it still governs that period.

    status  current             the act governs the period; nothing replaces it
            successor_in_force  an act that repeals it (in whole or in part) is in force for the period — review which
                                provisions apply; the register does not say which
            superseded          the register says the act ended before the period did — a later version governs it
    `on` is the date that decides (default: the period end); a regulation that governs disclosures by the date they are
    made passes the disclosure date. When a tracked act is replaced by another act the framework also tracks, that is
    the lineage moving on: the successor governs and the replaced act is listed under `lineage`, not raised.
    Amendments in force by that date are listed ("as amended by"). A register date that contradicts itself (an act
    shown in force yet 'ended' in the past) is reported, never acted on."""
    from sqlalchemy import text

    from services.regulatory_monitoring.eurlex_detector import FRAMEWORK_CELEX
    tracked = FRAMEWORK_CELEX.get(framework)
    if not tracked:
        return None
    period = period_end.isoformat() if isinstance(period_end, date) else str(period_end)[:10]
    pe = (on.isoformat() if isinstance(on, date) else str(on)[:10]) if on else period
    today = date.today().isoformat()
    snaps = {r["celex"]: r["signal"] or {} for r in session.execute(
        text("SELECT celex, signal FROM reg_source_snapshot WHERE celex = ANY(:c)"), {"c": tracked}).mappings()}
    rels = _relations(session, tracked)
    lineage = []
    for r in rels:                                            # tracked act replaced by a tracked successor, by `pe`
        starts = min(r["entry_into_force"]) if r["entry_into_force"] else None
        if r["relation"] != "amends" and r["related_celex"] in tracked and starts and starts <= pe:
            lineage.append({"replaced": r["celex"], "by": r["related_celex"], "since": starts})
    replaced_in_lineage = {x["replaced"] for x in lineage}
    not_yet = {cx for cx in tracked if cx not in replaced_in_lineage and (snaps.get(cx, {}).get("entry_into_force") or [None])[0]
               and min(snaps[cx]["entry_into_force"]) > pe}   # a successor that does not apply yet on `pe`
    not_yet |= {r["related_celex"] for r in rels if r["relation"] != "amends" and r["related_celex"] in tracked
                and (not r["entry_into_force"] or min(r["entry_into_force"]) > pe)}
    acts = [cx for cx in tracked if cx not in replaced_in_lineage and cx not in not_yet] or tracked[:1]
    governing, amended_by, replaced_by, notes = [], [], [], []
    status = "current"
    for cx in acts:
        sig = snaps.get(cx, {})
        eov = sig.get("end_of_validity")
        ended_at = None
        if eov and eov != _NO_END:
            if sig.get("in_force") and eov < today:
                notes.append(f"the register shows {cx} in force but also ended on {eov}; not acted on")
            else:
                ended_at = eov
        governing.append({"celex": cx, "title": act_meta(cx)["title"], "role": act_meta(cx)["role"],
                          "ended": ended_at})
        if ended_at and ended_at < pe:
            status = "superseded"
        for r in rels:
            if r["celex"] != cx:
                continue
            eif = r["entry_into_force"] or []
            starts = min(eif) if eif else None
            if not starts or starts > pe:
                continue
            item = {"celex": r["related_celex"], "title": short_title(r["title"], r["related_celex"]), "since": starts, "of": cx,
                    "url": f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{r['related_celex']}"}
            if r["relation"] == "amends":
                amended_by.append(item)
            elif r["related_celex"] in tracked:
                continue                                      # our own successor — handled as lineage
            else:
                replaced_by.append({**item, "relation": r["relation"]})
                if status == "current":
                    status = "successor_in_force"
    supported_until = None
    ends = [g["ended"] for g in governing if g["ended"]]
    if status == "superseded" and ends:
        supported_until = (date.fromisoformat(min(ends)) + timedelta(days=LEGACY_SUPPORT_DAYS)).isoformat()
    label = " · ".join(f"{g['title']} ({g['celex']})" for g in governing if g["role"] == "base") or acts[0]
    return {"framework": framework, "period_end": period, "decided_on": pe, "label": label, "governing": governing, "lineage": lineage,
            "amended_by": sorted(amended_by, key=lambda a: a["since"]), "replaced_by": replaced_by, "status": status,
            "supported_until": supported_until, "notes": notes}
