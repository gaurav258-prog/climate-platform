"""Regulator-anticipation model — "how your supervisors will read your data".

The Supervisory view's outward half: for each regulator that supervises an org's applicable frameworks, this
registry captures (a) the regulator's mission, (b) its supervisory focus areas — what it scrutinises and the
transparency it seeks — and (c) the concrete questions a preparer should expect, each mapped to the live figure
our engine already produces that answers it. Nothing here is fabricated: focus areas and questions are curated
from the cited supervisory texts, and every answer is pulled live from the org's own KRI values (or shown as
"produced in your filing" / "not produced yet" when there is no single headline number). It never invents a
value the platform did not compute.

Keyed to the platform's framework ids (see services/governance/reg_reference.py).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

# When the curated question library was last verified against the regulations. Shown as provenance; the
# per-supervisor "review recommended" flags below catch anything the regulator has moved since.
LIBRARY_REVIEWED = "January 2026"

# ── which supervisor reads each framework ───────────────────────────────────────────────────────────
FRAMEWORK_SUPERVISOR: dict[str, str] = {
    "bank_p3esg": "eba_ecb", "bank_tcfd": "eba_ecb",
    "insurer_climate": "eiopa",
    "sfdr_pai": "esas", "assetmgmt_tcfd": "esas",
    "csrd_e1": "nca_sustainability", "esrs_pack": "nca_sustainability", "reit_tcfd": "nca_sustainability",
    "eudr_dds": "ec_traces",
}

# ── the supervisors themselves — mission + supervisory focus (what they scrutinise · transparency sought) ──
SUPERVISORS: dict[str, dict] = {
    "eba_ecb": {
        "name": "EBA / ECB Banking Supervision",
        "jurisdiction": "EU · banking prudential supervision",
        "mission": "Ensure banks identify, disclose and prudently manage climate-related and environmental "
                   "(C&E) risks so they do not threaten safety and soundness.",
        "reference": "ECB Guide on climate-related and environmental risks (Nov 2020) · EBA ITS (EU) 2022/2453 · CRR Art. 449a",
        "focus_areas": [
            {"title": "Physical-risk concentration",
             "scrutiny": "Whether the banking book is over-concentrated in geographies and sectors exposed to acute and chronic climate hazards.",
             "transparency": "Gross carrying amount by NACE sector and geography, split acute vs chronic (Pillar 3 Template 5)."},
            {"title": "Green Asset Ratio credibility",
             "scrutiny": "Whether the GAR rests on the correct covered-asset denominator and real Taxonomy screening — not a headline number.",
             "transparency": "GAR on stock: eligible vs aligned, on the Art. 7 covered-assets basis (Templates 6–8)."},
            {"title": "Transition risk & financed emissions",
             "scrutiny": "Exposure to high-emitting counterparties and the coherence of counterparty transition plans.",
             "transparency": "Financed emissions (Scope 1–3) and the share of the book in high-climate-impact NACE sectors."},
            {"title": "Forward-looking risk",
             "scrutiny": "Whether the bank looks beyond a point-in-time snapshot to how exposures deteriorate under warming pathways.",
             "transparency": "Projected share of the book crossing into high risk under a 2°C / hot-house scenario."},
        ],
    },
    "eiopa": {
        "name": "EIOPA / national insurance supervisor",
        "jurisdiction": "EU · insurance prudential supervision",
        "mission": "Supervise the natural-catastrophe and climate exposure of underwriting and investments, and "
                   "monitor the widening climate protection gap.",
        "reference": "Solvency II (Dir. 2009/138/EC) climate-risk supervision · IFRS S2 · EIOPA NatCat / protection-gap work",
        "focus_areas": [
            {"title": "NatCat exposure & accumulation",
             "scrutiny": "The gross and net catastrophe exposure of the book, peril accumulation, and the modelled PML at extreme return periods.",
             "transparency": "Sum insured at risk by peril and geography; PML at a 1-in-200 return period."},
            {"title": "Underwriting resilience",
             "scrutiny": "Whether pricing, expected loss and reinsurance leave the balance sheet resilient to a severe catastrophe year.",
             "transparency": "Expected annual loss, loss ratio, and net retention after reinsurance."},
        ],
    },
    "esas": {
        "name": "ESAs (ESMA · EBA · EIOPA) — SFDR",
        "jurisdiction": "EU · sustainable-finance disclosure",
        "mission": "Ensure financial-market participants disclose the principal adverse impacts of their "
                   "investments completely and consistently, and prevent greenwashing.",
        "reference": "SFDR (EU) 2019/2088 Art. 4 · RTS (EU) 2022/1288 Annex I · ESAs greenwashing reports",
        "focus_areas": [
            {"title": "PAI completeness",
             "scrutiny": "Whether all 14 mandatory Principal Adverse Impact indicators are reported and how complete the underlying data is.",
             "transparency": "The Annex I PAI statement with data-coverage disclosed, not silently gap-filled."},
            {"title": "Greenwashing prevention",
             "scrutiny": "Consistency between disclosed sustainability metrics and how products are marketed.",
             "transparency": "Carbon footprint, GHG intensity and fossil-fuel exposure of the holdings, traceable to issuer data."},
        ],
    },
    "nca_sustainability": {
        "name": "National competent authority — sustainability reporting",
        "jurisdiction": "EU · CSRD/ESRS & Taxonomy Art. 8 assurance",
        "mission": "Ensure sustainability statements are prepared on a double-materiality basis, are complete and "
                   "XBRL-tagged, and that the anticipated financial effects of climate risk are disclosed.",
        "reference": "CSRD (EU) 2022/2464 · ESRS Delegated Reg. (EU) 2023/2772 · Taxonomy DA (EU) 2021/2178",
        "focus_areas": [
            {"title": "Double materiality (E1)",
             "scrutiny": "Whether material physical and transition climate risks to own operations are identified and quantified.",
             "transparency": "Asset value at risk and the resilience of the strategy under climate scenarios (ESRS E1)."},
            {"title": "Anticipated financial effects",
             "scrutiny": "Whether the financial effects of climate risk (e.g. cost of sourcing, business interruption) are estimated, not just narrated.",
             "transparency": "Quantified € effect — e.g. COGS at risk in the supply chain."},
            {"title": "Water & biodiversity (E3 / E4)",
             "scrutiny": "Whether dependencies on water-stressed basins and biodiversity-sensitive areas are disclosed.",
             "transparency": "Sites in water-stressed basins (E3) and sourcing in protected / sensitive areas (E4)."},
        ],
    },
    "ec_traces": {
        "name": "EU competent authorities · EC (TRACES)",
        "jurisdiction": "EU · deforestation-free supply chains",
        "mission": "Ensure operators placing in-scope commodities on the EU market submit a valid Due Diligence "
                   "Statement with geolocation and a deforestation-free / legality assessment.",
        "reference": "EU Deforestation Regulation (EU) 2023/1115 · Art. 33 (DDS) · Annex II",
        "focus_areas": [
            {"title": "Geolocation completeness",
             "scrutiny": "Whether every covered plot carries the required geolocation (polygons for plots > 4 ha).",
             "transparency": "Plot polygons on file for all covered plots."},
            {"title": "Deforestation-free assurance",
             "scrutiny": "Whether a deforestation-free determination against the 31-Dec-2020 cut-off exists for each covered plot.",
             "transparency": "Share of covered plots with a deforestation-free determination; any non-compliant / post-cutoff loss."},
        ],
    },
}

# ── the questions a preparer should expect, per framework — each mapped to the live figure that answers it ──
# `kri_key` (optional) pulls the org's live KRI value for that framework; `metric` (optional) names the figure
# that lives in the filing when there is no single headline KRI. `focus` matches a focus-area title above.
SUPERVISORY_QUESTIONS: dict[str, list[dict]] = {
    "bank_p3esg": [
        {"q": "What share of your banking book is in high-climate-impact (NACE A–H, L) sectors?",
         "focus": "Transition risk & financed emissions", "kri_key": "sector_concentration"},
        {"q": "How is your book split between acute and chronic physical hazards?",
         "focus": "Physical-risk concentration", "kri_key": "acute_share"},
        {"q": "What is your Green Asset Ratio — eligible vs aligned, on the covered-asset basis?",
         "focus": "Green Asset Ratio credibility", "metric": "Green Asset Ratio (Pillar 3 Templates 6–8)"},
        {"q": "How much of the book crosses into high physical risk under a 2°C / hot-house pathway?",
         "focus": "Forward-looking risk", "kri_key": "forward_share"},
        {"q": "What are your financed emissions across Scope 1–3?",
         "focus": "Transition risk & financed emissions", "kri_key": "fin_emissions"},
    ],
    "bank_tcfd": [
        {"q": "What is the Taxonomy eligibility and alignment (GAR) of your exposures?",
         "focus": "Green Asset Ratio credibility", "metric": "EU-Taxonomy eligibility & GAR (Art. 8)"},
        {"q": "What value of the book is at high climate risk today?",
         "focus": "Physical-risk concentration", "kri_key": "value_at_risk"},
        {"q": "How much of the book crosses into high physical risk under a warming pathway?",
         "focus": "Forward-looking risk", "kri_key": "forward_share"},
    ],
    "insurer_climate": [
        {"q": "What is your sum insured at high risk, by peril and geography?",
         "focus": "NatCat exposure & accumulation", "kri_key": "value_at_risk"},
        {"q": "What is your modelled NatCat capital at the 99.5% (≈1-in-200) level?",
         "focus": "NatCat exposure & accumulation", "kri_key": "natcat_scr"},
        {"q": "What is your expected annual catastrophe loss and loss ratio?",
         "focus": "Underwriting resilience", "kri_key": "eal"},
        {"q": "What is your net retention after reinsurance?",
         "focus": "Underwriting resilience", "kri_key": "net_retention"},
    ],
    "sfdr_pai": [
        {"q": "Are all 14 mandatory PAI indicators reported, and how complete is the data?",
         "focus": "PAI completeness", "metric": "PAI statement — Annex I Table 1 (14 mandatory indicators)"},
        {"q": "What is the GHG footprint / intensity of your holdings?",
         "focus": "Greenwashing prevention", "metric": "Carbon footprint & GHG intensity of investments"},
    ],
    "assetmgmt_tcfd": [
        {"q": "What is your portfolio climate value-at-risk?",
         "focus": "Greenwashing prevention", "kri_key": "climate_var"},
        {"q": "What is your concentration in the largest common-shock zone?",
         "focus": "PAI completeness", "kri_key": "common_shock"},
    ],
    "csrd_e1": [
        {"q": "What material physical climate risks affect your operations, and what asset value is at risk?",
         "focus": "Double materiality (E1)", "kri_key": "asset_at_risk"},
        {"q": "What are the anticipated financial effects — e.g. COGS at risk in your supply chain?",
         "focus": "Anticipated financial effects", "kri_key": "cogs_at_risk"},
        {"q": "What are your GHG emissions across Scope 1–3?",
         "focus": "Double materiality (E1)", "kri_key": "ghg_emissions"},
    ],
    "esrs_pack": [
        {"q": "What material physical climate risks affect your operations, and what asset value is at risk?",
         "focus": "Double materiality (E1)", "kri_key": "asset_at_risk"},
        {"q": "What are the anticipated financial effects — e.g. COGS at risk in your supply chain?",
         "focus": "Anticipated financial effects", "kri_key": "cogs_at_risk"},
        {"q": "Which sourcing sites sit in water-stressed basins (ESRS E3)?",
         "focus": "Water & biodiversity (E3 / E4)", "kri_key": "water_plots_stressed"},
        {"q": "Do you source from biodiversity-sensitive / protected areas (ESRS E4)?",
         "focus": "Water & biodiversity (E3 / E4)", "kri_key": "protected_area"},
    ],
    "reit_tcfd": [
        {"q": "What property value is at high climate risk?",
         "focus": "Double materiality (E1)", "kri_key": "value_at_risk"},
        {"q": "What is the net-operating-income impact of climate risk?",
         "focus": "Anticipated financial effects", "kri_key": "noi_impact"},
        {"q": "What resilience capex would de-risk the portfolio?",
         "focus": "Anticipated financial effects", "kri_key": "resilience_capex"},
    ],
    "eudr_dds": [
        {"q": "What share of covered plots have a deforestation-free determination?",
         "focus": "Deforestation-free assurance", "kri_key": "deforestation_free_pct"},
        {"q": "Are any plots non-compliant or in post-cutoff forest-loss areas?",
         "focus": "Deforestation-free assurance", "kri_key": "non_compliant"},
        {"q": "Do all covered plots over 4 ha carry a geolocation polygon?",
         "focus": "Geolocation completeness", "metric": "Plot polygons (EUDR Annex II geolocation)"},
    ],
}


def supervisory_anticipation(session: Session, org_id: str, org_type: str | None) -> dict:
    """For the org's applicable frameworks, group the supervisors that read them and answer each expected
    supervisory question with the org's own live figure (or a filing pointer). Honest by construction."""
    from services.governance.filings import reporting_requirements
    from services.governance.kri import kri, kri_frameworks
    from services.governance.reg_outlook import changes_affecting

    reqs = reporting_requirements(session, org_id, org_type)
    applicable = [r["framework"] for r in reqs]
    kfw = {f["framework"] for f in kri_frameworks(org_type)}

    grouped: dict[str, dict] = {}
    for fw in applicable:
        sid = FRAMEWORK_SUPERVISOR.get(fw)
        if not sid or sid not in SUPERVISORS:
            continue
        # pull this framework's live KRI values once
        kmap: dict[str, dict] = {}
        if fw in kfw:
            try:
                for k in (kri(session, org_id, fw).get("kpis") or []):
                    kmap[k["key"]] = k
            except Exception:
                pass
        # tie to the regulatory-change signal: any coming change touching this framework flags its questions
        fw_changes = changes_affecting(org_type, fw)
        entry = grouped.setdefault(sid, {"framework_ids": set(), "by_q": {}, "changes": {}})
        entry["framework_ids"].add(fw)
        for ch in fw_changes:
            entry["changes"].setdefault(ch["title"], ch)
        for q in SUPERVISORY_QUESTIONS.get(fw, []):
            answer = None
            kk = kmap.get(q.get("kri_key")) if q.get("kri_key") else None
            if kk is not None:
                answer = {"label": kk.get("label"), "value": kk.get("value"),
                          "fmt": kk.get("fmt"), "breached": bool(kk.get("breached"))}
            row = {"framework": fw, "question": q["q"], "focus": q["focus"],
                   "metric": q.get("metric"), "answer": answer, "answered": answer is not None,
                   "review": bool(fw_changes)}
            # dedupe identical questions across frameworks that share a supervisor — keep the answered one
            prev = entry["by_q"].get(q["q"])
            if prev is None or (not prev["answered"] and row["answered"]):
                entry["by_q"][q["q"]] = row

    supervisors = []
    for sid, e in grouped.items():
        s = SUPERVISORS[sid]
        questions = list(e["by_q"].values())
        changes = list(e["changes"].values())
        supervisors.append({
            "id": sid, "name": s["name"], "jurisdiction": s["jurisdiction"], "mission": s["mission"],
            "reference": s["reference"], "focus_areas": s["focus_areas"],
            "frameworks": sorted(e["framework_ids"]), "questions": questions,
            "answered": sum(1 for q in questions if q["answered"]), "total": len(questions),
            "review": {"needs_review": bool(changes), "changes": changes},
        })
    supervisors.sort(key=lambda x: x["name"])
    return {"supervisors": supervisors, "library_reviewed": LIBRARY_REVIEWED,
            "summary": {"n_supervisors": len(supervisors),
                        "n_questions": sum(s["total"] for s in supervisors),
                        "n_answered": sum(s["answered"] for s in supervisors),
                        "n_review": sum(1 for s in supervisors if s["review"]["needs_review"])}}
