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

Substantial contribution and minimum safeguards cannot be verified with data
this platform collects: substantial contribution needs technical screening
criteria (e.g. building floor area + EPC rating for real estate, or
generation-source mix for energy assets); minimum safeguards needs
counterparty-level OECD/ILO compliance diligence. Without these, "aligned"
can never be honestly claimed -- so this classifier only ever returns
"eligible" (the activity is described in Annex I at all) or "not_eligible"
(it isn't), never a fabricated "aligned". This mirrors the honesty
convention already established in ml/scoring/valuation_discount.py's
ltv_pct() -- an absent input produces an honest None/lesser status, never a
invented number.
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


def classify_taxonomy(
    nace_code: Optional[str],
    headline_bucket: Optional[str] = None,
    resilience_rating: Optional[str] = None,
) -> dict:
    """
    Returns {"status": "eligible"|"not_eligible", "activity_ref": str|None,
    "reasoning": {...}}. Never returns "aligned" -- see module docstring.

    headline_bucket/resilience_rating (if given) feed a DNSH-climate-adaptation
    diagnostic: Tellumen's own physical-risk score IS the kind of evidence a
    real Article 17 climate-adaptation DNSH check needs, so a High/Very High
    bucket with no documented resilience measures is flagged as a genuine
    concern -- but it's one data point among several unverified ones, not by
    itself sufficient to reach "aligned".
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

    reasoning = {
        "activity_described_in_annex_i": bool(activity_ref),
        "activity_ref": activity_ref,
        "substantial_contribution_verified": False,
        "substantial_contribution_note": (
            "Requires technical screening criteria data (e.g. building floor area + EPC "
            "rating, or generation-source mix) not currently collected."
        ),
        "minimum_safeguards_verified": False,
        "minimum_safeguards_note": (
            "Requires counterparty-level OECD Guidelines for MNEs / UN Guiding Principles / "
            "ILO core conventions compliance diligence not currently collected."
        ),
        "dnsh_climate_adaptation_flag": None,
    }

    if headline_bucket in ("VH", "H") and not resilience_rating:
        reasoning["dnsh_climate_adaptation_flag"] = (
            "This asset's own physical-risk score is High/Very High with no documented "
            "adaptation measures on record -- a real DNSH-climate-adaptation concern "
            "(Article 17), though this alone does not determine overall alignment."
        )

    return {"status": status, "activity_ref": activity_ref, "reasoning": reasoning}
