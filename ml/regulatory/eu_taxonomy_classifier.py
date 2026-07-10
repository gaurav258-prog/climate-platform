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


# Only mapped where a specific Annex I section genuinely, directly covers the
# NACE activity -- no forced matches. Checked against the 7 demo sectors'
# real NACE codes; extend this table as real NACE codes are encountered.
NACE_ANNEX_I_ELIGIBILITY = {
    "68.20": "Climate Delegated Act (EU) 2021/2139, Annex I §7.7 — Acquisition and ownership of buildings",
    "35.11": "Climate Delegated Act (EU) 2021/2139, Annex I §4 — Electricity, gas, steam and air conditioning supply",
}

# EPC A/B is a defensible, disclosed proxy for "substantial contribution" under
# Annex I §7.7's technical screening criteria (top-of-market energy performance) --
# NOT the full criteria (which also allow a top-15%-of-national-stock or a
# qualifying-renovation route this simple grade check can't evaluate). Treated
# as a documented simplification, not a certified assessment -- see reasoning.note.
EPC_MEETS_SUBSTANTIAL_CONTRIBUTION = {"A", "B"}


def classify_taxonomy(
    nace_code: Optional[str],
    headline_bucket: Optional[str] = None,
    resilience_rating: Optional[str] = None,
    epc_rating: Optional[str] = None,
    minimum_safeguards_status: Optional[str] = None,
) -> dict:
    """
    Returns {"status": "eligible"|"not_eligible", "activity_ref": str|None,
    "reasoning": {...}}. Never returns "aligned" -- see module docstring
    (DNSH across the other five environmental objectives is never assessed
    here, regardless of what evidence is supplied).

    headline_bucket/resilience_rating (if given) feed a DNSH-climate-adaptation
    diagnostic: Tellumen's own physical-risk score IS the kind of evidence a
    real Article 17 climate-adaptation DNSH check needs, so a High/Very High
    bucket with no documented resilience measures is flagged as a genuine
    concern -- but it's one data point among several unverified ones, not by
    itself sufficient to reach "aligned".

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

    activity_ref = NACE_ANNEX_I_ELIGIBILITY.get(nace_code)
    status = "eligible" if activity_ref else "not_eligible"

    if epc_rating:
        substantial_contribution_verified = epc_rating in EPC_MEETS_SUBSTANTIAL_CONTRIBUTION
        substantial_contribution_note = (
            f"EPC {epc_rating} supplied — treated as meeting Annex I §7.7's substantial-"
            f"contribution bar (a disclosed simplification of the full technical screening "
            f"criteria; the top-15%-of-stock and qualifying-renovation routes aren't evaluated)."
            if substantial_contribution_verified else
            f"EPC {epc_rating} supplied — below the A/B threshold this simplified check uses, "
            f"so substantial contribution is not considered met (though the full technical "
            f"screening criteria's other routes weren't evaluated either)."
        )
    else:
        substantial_contribution_verified = False
        substantial_contribution_note = (
            "Requires technical screening criteria data (e.g. building EPC rating, or "
            "generation-source mix) not currently supplied for this entity."
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
        "substantial_contribution_verified": substantial_contribution_verified,
        "substantial_contribution_note": substantial_contribution_note,
        "minimum_safeguards_verified": minimum_safeguards_verified,
        "minimum_safeguards_note": minimum_safeguards_note,
        "dnsh_climate_adaptation_flag": None,
    }

    if headline_bucket in ("VH", "H") and not resilience_rating:
        reasoning["dnsh_climate_adaptation_flag"] = (
            "This asset's own physical-risk score is High/Very High with no documented "
            "adaptation measures on record -- a real DNSH-climate-adaptation concern "
            "(Article 17), though this alone does not determine overall alignment."
        )

    return {"status": status, "activity_ref": activity_ref, "reasoning": reasoning}
