"""CRCS · regulation version register (N-1 lifecycle).

For each framework a client files, this reconstructs the regulation's version lineage — the base act and the
amendments that have changed it — from the live EUR-Lex (Cellar) snapshots the detector already holds. It shows
which version is in force now, the effective-date milestones (past and upcoming), and whether an older basis is
being superseded. This is the "know exactly which version you're filing against, and what's coming" pillar of
the Continuous Regulatory Compliance System. Dates are live from the register; nothing is guessed.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

# curated identity for each tracked act (title + its role in the lineage) — the dates come live from Cellar.
ACT_META: dict[str, dict] = {
    "32023R1115": {"title": "EU Deforestation Regulation (EUDR)", "role": "base"},
    "32024R3234": {"title": "EUDR — application-date amendment", "role": "amendment"},
    "32021R2178": {"title": "Taxonomy Disclosures Delegated Act", "role": "base"},
    "32022R2453": {"title": "Pillar 3 ESG — ITS", "role": "base"},
    "32022R1288": {"title": "SFDR Regulatory Technical Standards", "role": "base"},
    "32019R2088": {"title": "SFDR (base Regulation)", "role": "base"},
    "32023R2772": {"title": "ESRS Delegated Act", "role": "base"},
    "32022L2464": {"title": "CSRD Directive", "role": "base"},
    "32009L0138": {"title": "Solvency II Directive", "role": "base"},
}


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
    from services.governance.filings import FRAMEWORKS
    from services.governance.reg_reference import REFERENCE
    from services.regulatory_monitoring.eurlex_detector import FRAMEWORK_CELEX
    from sqlalchemy import text

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
            am = ACT_META.get(cx, {"title": cx, "role": "base"})
            if ck:
                checked = ck.date().isoformat()
            acts.append({
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
