"""Business interruption at the company's own sites, on its stated method (E69).

BI at risk = the site's annual throughput × the share of the year the company expects the site to be down from its
headline hazard (method.bi_downtime_share, by peril and the hazard band of the site's score — the company's own,
attested for the financial year). The platform supplies no downtime curve: an unstated share is a named gap, and a
site with no throughput or no score is not assessed — never a number.
"""
from __future__ import annotations

from core.types import score_to_bucket


def bi_at_risk(method, throughput_eur: float | None, hazard: str | None, score: float | None) -> dict:
    """{'bi_at_risk_eur': x} — or {'bi_at_risk_eur': None, 'reason': 'no_throughput' | 'unscored'} — or a 'gap'."""
    if not throughput_eur:
        return {"bi_at_risk_eur": None, "reason": "no_throughput"}
    if score is None or hazard is None:
        return {"bi_at_risk_eur": None, "reason": "unscored"}
    band = score_to_bucket(score).value
    share = method.per_peril("method.bi_downtime_share", hazard, band)
    if share is None:
        return {"bi_at_risk_eur": None, "gap": f"not stated: method.bi_downtime_share ({hazard}/{band})"}
    return {"bi_at_risk_eur": round(throughput_eur * share), "downtime_share": share}


def sites_bi(method, sites: list[dict]) -> dict:
    """Per site (in place: bi_at_risk_eur, bi_gap) and the total — the total is a gap if any scored site with a
    throughput is, never a partial sum."""
    gaps, total = set(), 0.0
    for s in sites:
        r = bi_at_risk(method, s.get("throughput_eur"), s.get("top_hazard"), s.get("hazard_score"))
        s["bi_at_risk_eur"] = r["bi_at_risk_eur"]
        if r.get("gap"):
            s["bi_gap"] = r["gap"]
            gaps.add(r["gap"].removeprefix("not stated: "))
        elif r["bi_at_risk_eur"] is not None:
            total += r["bi_at_risk_eur"]
    return {"bi_at_risk_eur": None, "gap": "not stated: " + ", ".join(sorted(gaps))} if gaps else {"bi_at_risk_eur": round(total)}
