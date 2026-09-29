"""EU Taxonomy alignment of a building owned — activity 7.7 'Acquisition and ownership of buildings' (Delegated
Regulation (EU) 2021/2139, Annex I §7.7 and Appendix A), from the criteria as captured
(data/reference/taxonomy/criteria/ccm_7_7.json) and the building's stated facts.

Each criterion is met (True), not met (False) or not known (None) — never guessed:
  substantial contribution — built before 2021: EPC class A, or evidenced top 15 % of the stock by operational primary
    energy demand; built after 2020: the Section 7.1 criteria; and, for a large non-residential building (heating /
    air-conditioning over 290 kW), energy-performance monitoring
  do no significant harm — climate adaptation by Appendix A: a climate risk and vulnerability assessment (the platform's
    physical-risk assessment of the building, a declared reading) and an adaptation plan; the other four objectives are
    'N/A' for this activity
  minimum safeguards — Regulation (EU) 2020/852 Art. 18, as the undertaking states
Aligned when all three are met; not aligned when any is not; otherwise not known.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_FILE = Path(__file__).resolve().parents[2] / "data" / "reference" / "taxonomy" / "criteria" / "ccm_7_7.json"


@lru_cache(maxsize=1)
def criteria() -> dict:
    return json.loads(_FILE.read_text())


def _all(parts: list[bool | None]) -> bool | None:
    if any(p is False for p in parts):
        return False
    return None if any(p is None for p in parts) else True


def evaluate(p: dict) -> dict:
    """{'substantial_contribution', 'dnsh_adaptation', 'minimum_safeguards', 'aligned': True | False | None,
    'reasons': [...]} for one building (a property row of the frozen book)."""
    c = criteria()
    reasons: list[str] = []
    year = p.get("year_built")
    epc = (p.get("epc_rating") or "").strip().upper() or None
    if year is None:
        sc_age = None
        reasons.append("year built not stated — which substantial-contribution test applies is unknown")
    elif int(year) <= 2020:
        if epc == "A" or p.get("ped_top15_evidence") is True:
            sc_age = True
        elif epc is not None and p.get("ped_top15_evidence") is False:
            sc_age = False
            reasons.append(f"built {year}: EPC {epc} (not A) and not in the top 15 % by primary energy demand")
        else:
            sc_age = None
            reasons.append(f"built {year}: EPC {epc or 'not stated'}; top-15 % primary-energy evidence not stated")
    else:
        sc_age = p.get("meets_new_building_criteria")
        if sc_age is None:
            reasons.append(f"built {year}: whether it meets the Section 7.1 criteria is not stated")
        elif sc_age is False:
            reasons.append(f"built {year}: does not meet the Section 7.1 criteria")
    ptype = (p.get("property_type") or "").strip().lower()
    kinds = c["property_types"]
    residential = True if ptype in kinds["residential"] else False if ptype in kinds["non_residential"] else None
    kw = p.get("heating_rated_output_kw")
    threshold = next(s["large_threshold_kw"] for s in c["substantial_contribution"] if s["id"] == "sc3")
    large = False if residential is True or (kw is not None and float(kw) <= threshold) else \
        True if (residential is False and kw is not None and float(kw) > threshold) else None
    if large is None:
        sc_large = None
        reasons.append("whether it is a large non-residential building (over 290 kW) is not known")
    elif large:
        sc_large = p.get("energy_performance_monitoring")
        if sc_large is not True:
            reasons.append("large non-residential building: energy-performance monitoring "
                           + ("not in place" if sc_large is False else "not stated"))
    else:
        sc_large = True
    sc = _all([sc_age, sc_large])
    assessed = bool(p.get("hazards") or p.get("headline_bucket"))
    plan = p.get("adaptation_plan_in_place")
    dnsh = _all([assessed or None, plan])
    if not assessed:
        reasons.append("no climate risk and vulnerability assessment of the building on record")
    if plan is not True:
        reasons.append("adaptation plan " + ("not in place" if plan is False else "not stated"))
    ms_status = p.get("minimum_safeguards_status")
    ms = True if ms_status == "compliant" else False if ms_status == "non_compliant" else None
    if ms is not True:
        reasons.append("minimum safeguards " + ("not met" if ms is False else "not stated"))
    return {"substantial_contribution": sc, "dnsh_adaptation": dnsh, "minimum_safeguards": ms,
            "aligned": _all([sc, dnsh, ms]), "reasons": reasons}
