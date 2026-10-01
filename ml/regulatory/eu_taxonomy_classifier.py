"""
EU Taxonomy Regulation (EU) 2020/852, Article 3 classification -- Climate
Change Mitigation objective only (Annex I of the Climate Delegated Act,
Commission Delegated Regulation (EU) 2021/2139). Climate Change Adaptation
(Annex II) and the four other environmental objectives (added later, 2023)
have entirely separate activity lists and are out of scope here.

Article 3 requires ALL FOUR conditions for "aligned": (a) substantial
contribution to an environmental objective per the technical screening
criteria, (b) do-no-significant-harm (DNSH) to the other five objectives
(Article 17), (c) minimum safeguards -- OECD Guidelines for MNEs, UN Guiding
Principles on Business and Human Rights, ILO core conventions (Article 18),
(d) compliance with the Commission's technical screening criteria.

Substantial contribution and minimum safeguards historically couldn't be
verified with data this platform collected: substantial contribution needs
technical screening criteria (e.g. building EPC rating for real estate, or
generation-source mix for energy assets); minimum safeguards needs
counterparty-level OECD/ILO compliance diligence. Both can now be SUPPLIED
per-entity (epc_rating, minimum_safeguards_status -- see the
e6f7a8b9c0d1 migration) when a tenant has the data, but the classifier's
overall status STILL never returns "aligned" even when both are provided:
DNSH (Article 17) requires no significant harm across ALL SIX environmental
objectives, and this platform only ever evaluates one of them (climate
adaptation, via the physical-risk score) -- the other five (water, circular
economy, pollution, biodiversity, and climate mitigation itself for a
non-mitigation activity) are never assessed. So "aligned" would still be a
fabricated claim even with EPC + safeguards data in hand. What DOES change
when the data is supplied: reasoning.substantial_contribution_verified and
reasoning.minimum_safeguards_verified flip from False to True/False (a real,
checkable answer instead of "not collected"), which is real, disclosed
progress toward a genuine third-party alignment assessment -- just not the
assessment itself. This mirrors the honesty convention already established
in ml/scoring/valuation_discount.py's ltv_pct() -- an absent input produces
an honest None/lesser status, never an invented number.
"""
from __future__ import annotations

from typing import Optional

# Which activity a NACE code decides comes from the Taxonomy's own activity list (services/reference/
# taxonomy_activities.py, captured from the Delegated Acts): eligible only where every activity listing the code is the
# same activity. The former typed table marked every NACE 35.11 exposure eligible under a non-existent 'Annex I §4';
# electricity generation is several activities (solar, wind, gas, …), and coal generation none (error log E30).

# Annex I §7.7 point 1 (verified verbatim): for buildings built before 31 Dec 2020,
# the building must have AT LEAST EPC class A -- B does NOT qualify. (The regulation's
# own alternative route is the top 15% of the national/regional building stock, which
# this platform cannot evaluate from an EPC letter grade alone -- see reasoning.note.)
EPC_MEETS_SUBSTANTIAL_CONTRIBUTION = {"A"}


def classify_taxonomy(
    nace_code: Optional[str],
    material_physical_risk: Optional[bool] = None,
    resilience_rating: Optional[str] = None,
    epc_rating: Optional[str] = None,
    minimum_safeguards_status: Optional[str] = None,
) -> dict:
    """
    Returns {"status": "eligible"|"not_eligible"|"not_determined"|"not_assessed", "activity_ref": str|None,
    "reasoning": {...}}. Never returns "aligned" -- see module docstring
    (DNSH across the other five environmental objectives is never assessed
    here, regardless of what evidence is supplied).

    material_physical_risk (the asset's headline score at or above the
    institution's stated at-risk level — True/False, or None when the level is
    not stated) and resilience_rating feed a DNSH-climate-adaptation
    diagnostic: a material physical risk with no documented resilience measures
    is flagged as a genuine concern -- one data point among several unverified
    ones, not by itself sufficient to reach "aligned".

    epc_rating (real estate's building EPC grade, if supplied on upload) and
    minimum_safeguards_status ('compliant'/'non_compliant', a counterparty ESG-
    vendor flag, if supplied) let reasoning.substantial_contribution_verified /
    minimum_safeguards_verified become real answers instead of "not collected"
    -- see module docstring for why this still doesn't flip status to "aligned".
    """
    if not nace_code:
        return {
            "status": "not_assessed",
            "activity_ref": None,
            "reasoning": {
                "activity_described_in_annex_i": None,
                "activity_ref": None,
                "note": "No NACE code on record -- classification requires one.",
            },
        }

    from services.reference.taxonomy_activities import activity_for
    found = activity_for(nace_code)
    if found["status"] == "determined":
        status = "eligible"
        activity_ref = f"{' / '.join(found['codes'])} — {found['title']}"
    elif found["status"] == "not_determined":
        # the NACE code is listed by several different activities: which one the undertaking performs (and so
        # whether it is eligible at all) is not decided by its NACE code
        status, activity_ref = "not_determined", None
    else:
        status, activity_ref = "not_eligible", None
    is_buildings = found.get("section") == "7.7"             # the §7.7 EPC test applies to that activity only

    if epc_rating and is_buildings:
        substantial_contribution_verified = epc_rating in EPC_MEETS_SUBSTANTIAL_CONTRIBUTION
        substantial_contribution_note = (
            f"EPC {epc_rating} supplied — meets Annex I §7.7 point 1's substantial-contribution "
            f"bar (EPC class A is the primary criterion). The regulation's alternative route "
            f"(top 15% of the national/regional building stock) is a separate test this platform "
            f"does not evaluate."
            if substantial_contribution_verified else
            f"EPC {epc_rating} supplied — does NOT meet Annex I §7.7 point 1's substantial-"
            f"contribution bar, which requires EPC class A (not B or below). The regulation's "
            f"alternative route (top 15% of the national/regional building stock) is a separate, "
            f"unevaluated test this platform cannot check from an EPC letter grade alone -- so a "
            f"property below A is not confirmed ineligible via that route, only via this one."
        )
    else:
        substantial_contribution_verified = False
        substantial_contribution_note = (
            "Requires the technical screening criteria of the activity (e.g. a building's EPC rating for §7.7, or "
            "the generation source for electricity), not currently supplied for this entity."
        )

    if minimum_safeguards_status:
        minimum_safeguards_verified = minimum_safeguards_status == "compliant"
        minimum_safeguards_note = (
            f"Counterparty compliance status supplied: {minimum_safeguards_status} "
            f"(per the tenant's own OECD/UN/ILO screening)."
        )
    else:
        minimum_safeguards_verified = False
        minimum_safeguards_note = (
            "Requires counterparty-level OECD Guidelines for MNEs / UN Guiding Principles / "
            "ILO core conventions compliance diligence not currently supplied for this entity."
        )

    reasoning = {
        "activity_described_in_annex_i": bool(activity_ref),
        "activity_ref": activity_ref,
        "candidate_activities": [a["code"] + " " + a["title"] for a in found["activities"]][:20],
        "nace_basis": {"determined": "every Taxonomy activity listing this NACE code is the same activity",
                       "not_determined": "several different Taxonomy activities list this NACE code — the activity "
                                         "performed decides eligibility",
                       "none": "no Taxonomy activity of the Delegated Acts lists this NACE code"}[found["status"]],
        "substantial_contribution_verified": substantial_contribution_verified,
        "substantial_contribution_note": substantial_contribution_note,
        "minimum_safeguards_verified": minimum_safeguards_verified,
        "minimum_safeguards_note": minimum_safeguards_note,
        "dnsh_climate_adaptation_flag": None,
    }

    if material_physical_risk is None:
        reasoning["dnsh_climate_adaptation_gap"] = "not stated: method.at_risk_level"
    elif material_physical_risk and not resilience_rating:
        reasoning["dnsh_climate_adaptation_flag"] = (
            "This asset's physical-risk score is at or above the institution's stated at-risk level with no "
            "documented adaptation measures on record -- a real DNSH-climate-adaptation concern "
            "(Article 17), though this alone does not determine overall alignment."
        )

    return {"status": status, "activity_ref": activity_ref, "reasoning": reasoning}
