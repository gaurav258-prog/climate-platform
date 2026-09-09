"""What a regulatory change touches — the links from a framework to the governed things that depend on it.

A detected amendment to a framework is only actionable when it names what it may change here: the interpretation
switches whose method the framework prescribes, the KRIs and the regulatory datapoints they feed, the official
template the filing is built on, and the mandates in the registry that cite the act. All of that already exists as
configuration (interpretation schema, KRI→datapoint map, reporting reference, mandate registry); this module joins
it so a change opens on the surfaces it affects. Nothing is inferred from text: a link exists only where the
configuration declares the framework.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text


def links_for(framework: str, org_type: Optional[str] = None) -> dict:
    from services.calc_settings import INTERPRETATION_SCHEMA
    from services.governance.kri_regmap import KRI_REG
    from services.governance.reg_reference import REFERENCE
    from services.supervision.mandates import registry
    switches = [{"key": k, "label": v["label"], "sectors": v.get("sectors")} for k, v in INTERPRETATION_SCHEMA.items()
                if framework in (v.get("frameworks") or []) and (not org_type or not v.get("sectors") or org_type in v["sectors"])]
    kris = [{"key": k, "datapoint": dp, "tier": tier} for k, (dp, tier) in (KRI_REG.get(framework) or {}).items()]
    ref = REFERENCE.get(framework) or {}
    template = {"official_form": ref.get("official_form"), "form_url": ref.get("form_url"), "legal_basis": ref.get("legal_basis"), "authority": ref.get("authority")} if ref else None
    mandates = [{"id": m["id"], "title": m.get("title") or m.get("label"), "article": (m.get("article") or {}).get("ref"), "channel": (m.get("deliverable") or {}).get("channel_id")}
                for m in registry()["mandates"] if (m.get("deliverable") or {}).get("framework") == framework]
    return {"framework": framework, "switches": switches, "kris": kris, "template": template, "mandates": mandates,
            "n": len(switches) + len(kris) + (1 if template else 0) + len(mandates)}


def change_impacts(session, org_id: str, org_type: Optional[str]) -> dict:
    """Every open detected change to a framework this organisation reports under, with what it touches."""
    from services.governance.filings import available_frameworks
    from services.regulatory_monitoring.eurlex_detector import detected_changes
    mine = {f["framework"] for f in available_frameworks(org_type or "")}
    out = []
    for ch in detected_changes(session):
        if ch["framework"] not in mine:
            continue
        L = links_for(ch["framework"], org_type)
        alert = session.execute(text("SELECT task_id::text FROM reg_alert WHERE org_id = CAST(:o AS uuid) AND framework = :f AND kind = 'detected' ORDER BY raised_at DESC LIMIT 1"),
                                {"o": org_id, "f": ch["framework"]}).scalar()
        out.append({**ch, "touches": L, "task_id": alert})
    return {"changes": out, "frameworks": sorted(mine), "links": {fw: links_for(fw, org_type) for fw in sorted(mine)}, "note": "Links come from configuration only: a switch, KRI, template or mandate is listed when it declares the framework the change amends."}


def summary_text(framework: str, org_type: Optional[str]) -> str:
    L = links_for(framework, org_type)
    parts = []
    if L["switches"]:
        parts.append(f"{len(L['switches'])} interpretation switch(es): " + ", ".join(x["label"] for x in L["switches"]))
    if L["kris"]:
        parts.append(f"{len(L['kris'])} KRI datapoint(s) incl. " + ", ".join(x["datapoint"] for x in L["kris"][:3]))
    if L["template"] and L["template"].get("official_form"):
        parts.append("template: " + L["template"]["official_form"])
    if L["mandates"]:
        parts.append(f"{len(L['mandates'])} mandate(s) in the registry")
    return "Touches — " + "; ".join(parts) if parts else "Touches nothing configured for this framework yet."
