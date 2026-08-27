"""Coverage roadmap — what regulations we cover today, what we're building, and what's planned.

The forward half of "regulatory maintenance": a customer sees, per applicable sector, which frameworks are
LIVE, which are BUILDING (and roughly when), and which are PLANNED — plus, for anything not yet live, whether
they'll need to prepare new DATA or INTEGRATIONS in their environment. This is our own delivery plan, stated
honestly: "live" means we file it now; "building"/"planned" carry a target that is our intent, not a
regulatory promise, and anything gated on an external dependency says so.

Static registry — the single source of truth for the Roadmap tab. `sectors: None` = applies to every sector.
"""
from __future__ import annotations

# status: live | building | planned
ROADMAP: list[dict] = [
    # ── LIVE — we file these today ──────────────────────────────────────────────────────────────────
    {"id": "pillar3", "name": "Pillar 3 ESG (EBA prudential templates)", "status": "live", "sectors": ["bank"],
     "whats": "Templates 1/3/4/5 physical & transition risk + Green Asset Ratio (Templates 6–8), to the exact ITS structure.",
     "prep": None, "citation": "ITS (EU) 2022/2453 · CRR Art. 449a", "target": "Live"},
    {"id": "bank_tcfd", "name": "TCFD + EU Taxonomy Art. 8 (banking)", "status": "live", "sectors": ["bank"],
     "whats": "Taxonomy eligibility/alignment (GAR) with TCFD governance, strategy, risk & metrics.",
     "prep": None, "citation": "Taxonomy Reg. 2020/852 Art. 8 · DA 2021/2178", "target": "Live"},
    {"id": "insurer", "name": "Climate / NatCat exposure (insurer)", "status": "live", "sectors": ["insurer"],
     "whats": "Sum insured at risk, EAL, loss ratio and modelled PML by peril and geography.",
     "prep": None, "citation": "Solvency II · IFRS S2", "target": "Live"},
    {"id": "sfdr", "name": "SFDR Principal Adverse Impacts", "status": "live", "sectors": ["asset_manager"],
     "whats": "The 14 mandatory PAI indicators on the RTS Annex I statement.",
     "prep": None, "citation": "SFDR 2019/2088 Art. 4 · RTS 2022/1288", "target": "Live"},
    {"id": "csrd_esrs", "name": "CSRD — ESRS E1/E3/E4 (Climate · Water · Biodiversity)", "status": "live", "sectors": ["manufacturer"],
     "whats": "The environmental ESRS topical standards from your own sites + upstream sourcing.",
     "prep": None, "citation": "CSRD 2022/2464 · ESRS DA 2023/2772", "target": "Live"},
    {"id": "eudr", "name": "EUDR Due Diligence Statement", "status": "live", "sectors": ["manufacturer"],
     "whats": "Plot geolocation + deforestation-free / legality determination, assembled to the DDS content.",
     "prep": None, "citation": "EUDR (EU) 2023/1115 Art. 33", "target": "Live"},
    {"id": "reit_tcfd", "name": "TCFD + Taxonomy Art. 8 (property)", "status": "live", "sectors": ["reit"],
     "whats": "Taxonomy eligibility/alignment and TCFD physical & transition risk for the property portfolio.",
     "prep": None, "citation": "Taxonomy DA 2021/2178", "target": "Live"},

    # ── BUILDING — under active development, with a target and any prep you'll need ────────────────────
    {"id": "taxo_env", "name": "EU Taxonomy — 4 environmental objectives", "status": "building",
     "sectors": ["bank", "reit", "manufacturer"],
     "whats": "Extend Taxonomy alignment beyond climate to water, circular economy, pollution and biodiversity objectives.",
     "prep": "You'll provide activity-level data against the 4 additional objectives — no new integration.",
     "citation": "Environmental Delegated Act (EU) 2023/2486", "target": "target Q3 2026"},
    {"id": "esrs_xbrl", "name": "ESRS digital tagging (XBRL)", "status": "building", "sectors": ["manufacturer"],
     "whats": "Machine-readable XBRL tagging of the ESRS statement in the EFRAG taxonomy.",
     "prep": "No new data — we tag what you already file; you'll export the tagged instance.",
     "citation": "EFRAG ESRS XBRL taxonomy", "target": "target Q2 2026"},
    {"id": "traces_live", "name": "EUDR live submission to TRACES", "status": "building", "sectors": ["manufacturer"],
     "whats": "Submit the Due Diligence Statement directly into the EC TRACES system, not just assemble it.",
     "prep": "Integration: a TRACES operator registration + API credentials in your environment.",
     "citation": "EUDR Art. 33 · EC TRACES", "target": "gated on TRACES access"},

    # ── PLANNED — on the roadmap, not started ─────────────────────────────────────────────────────────
    {"id": "eba_dpm", "name": "EBA supervisory reporting (DPM export)", "status": "planned", "sectors": ["bank", "insurer"],
     "whats": "Direct EBA Data Point Model export for supervisory submission.",
     "prep": "Maps to your existing book; no new data expected.",
     "citation": "EBA reporting framework / DPM", "target": "planned 2026"},
    {"id": "issb", "name": "IFRS S2 / ISSB adoption", "status": "planned", "sectors": None,
     "whats": "IFRS S2 climate disclosures as jurisdictions adopt the ISSB standards.",
     "prep": "Reuses your climate physical & transition data.",
     "citation": "IFRS S2", "target": "planned · jurisdiction-dependent"},
]

_ORDER = {"live": 0, "building": 1, "planned": 2}


def roadmap(org_type: str | None) -> dict:
    """Roadmap items relevant to this sector (plus any that apply to all), grouped by status."""
    items = [r for r in ROADMAP if r["sectors"] is None or (org_type in (r["sectors"] or []))]
    items.sort(key=lambda r: (_ORDER.get(r["status"], 9), r["name"]))
    groups = {s: [r for r in items if r["status"] == s] for s in ("live", "building", "planned")}
    return {"groups": groups,
            "summary": {"live": len(groups["live"]), "building": len(groups["building"]), "planned": len(groups["planned"])}}
