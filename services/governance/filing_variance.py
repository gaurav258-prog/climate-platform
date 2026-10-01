"""Variance vs prior — decompose how a filing's numbers moved since the last one.

A reviewer approves *deltas*, not absolutes, and a regulator asks "why did this move?". This compares a
filing's frozen snapshot to a prior one (the version it restates, else the previous period's filing) and
decomposes the change: the headline shifts, the per-hazard exposure shifts, and the assets driving them —
newly at risk, no longer at risk, and the biggest score movers. Reads frozen snapshots only, so the answer
is stable and reproducible; nothing is invented — an asset absent from one side is reported as added/removed.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from services.governance.filings import get_filing, prior_filing_id
from services.governance.money_format import presentation_of
from services.governance.pillar3_templates import stated_level


def _asset_map(payload: dict, cfg: dict) -> dict:
    out = {}
    for a in payload.get(cfg["list"]) or []:
        out[a.get(cfg["id"])] = {
            "name": a.get(cfg["name"]), "value_eur": a.get(cfg["value"]) or 0,
            "score": a.get("headline_score"), "bucket": a.get("headline_bucket"),
        }
    return out


def _delta(now, prior):
    """now / prior / delta — a side that is a gap stays None, and so does the delta (never read as 0)."""
    return {"now": None if now is None else round(now), "prior": None if prior is None else round(prior),
            "delta": None if now is None or prior is None else round(now - prior)}


def _at(a: dict | None, level: float | None) -> bool | None:
    """At material physical risk on that filing's own stated level; None when its level was not stated."""
    if a is None:
        return False
    if level is None:
        return None
    return a["score"] is not None and a["score"] >= level


def variance(session: Session, org_id: str, filing_id: str, vs_filing_id: str | None = None) -> dict:
    cur = get_filing(session, org_id, filing_id, with_payload=True)
    if not cur:
        raise ValueError("filing not found")
    prior_id = vs_filing_id or prior_filing_id(session, org_id, filing_id)
    if not prior_id:
        return {"supported": False, "message": "No prior filing to compare against — this is the first of its kind."}
    prior = get_filing(session, org_id, prior_id, with_payload=True)
    if not prior:
        return {"supported": False, "message": "The comparison filing could not be loaded."}
    from services.governance.filing_lineage import _LIST_CFG
    cfg = _LIST_CFG.get(cur["framework"])
    if not cfg or prior["framework"] != cur["framework"]:
        return {"supported": False, "framework": cur["framework"],
                "message": "Variance decomposition is available for the located-book filings (loan book, "
                           "property book, underwriting book)."}

    cp = (cur.get("snapshot") or {}).get("payload") or {}
    pp = (prior.get("snapshot") or {}).get("payload") or {}
    if cur["framework"] == "bank_tcfd":                 # E95: the Taxonomy templates print their own T-1 columns
        from services.governance.bank_taxonomy_report import is_earlier_shape
        if not (is_earlier_shape(cp) and is_earlier_shape(pp)):
            return {"supported": False, "framework": cur["framework"], "prior_filing_id": prior_id,
                    "message": "The EU Taxonomy Art. 8 templates print no physical-risk figure to decompose; the "
                               "templates themselves carry the previous disclosure reference date (T-1) columns."}
    # multi-currency phase 3: a movement between filings in different currencies would mix exchange rates with risk
    cc, pc = presentation_of(cp), presentation_of(pp)
    if cc != pc:
        return {"supported": False, "framework": cur["framework"], "prior_filing_id": prior_id,
                "message": f"This filing presents in {cc} and the one before it in {pc} — their figures can't be "
                           f"subtracted. Compare against a filing in {cc}."}
    return {
        "supported": True, "filing_id": filing_id, "prior_filing_id": prior_id, "framework": cur["framework"],
        "currency": cc,
        "basis": {"current": {"period": cur["period_label"], **(cur.get("snapshot") or {}).get("reporting_basis", {})},
                  "prior": {"period": prior["period_label"], **(prior.get("snapshot") or {}).get("reporting_basis", {})}},
        **decompose(cp, pp, cfg),
    }


def decompose(cp: dict, pp: dict, cfg: dict | None = None) -> dict:
    """Pure decomposition of a current vs prior located-book payload — headline shifts, per-hazard exposure
    shifts, and the entities driving them. Total & value-at-risk are computed from the entity list (so it's
    sector-agnostic: loan book / property book / underwriting book). 'At risk' on each side is that filing's own stated
    level (method.at_risk_level, frozen with it); a change of level between the two is reported, never hidden in the
    movement. No DB, so it's unit-testable."""
    if cfg is None:   # default to the loan-book shape (keeps existing callers/tests working)
        from services.governance.filing_lineage import _LIST_CFG
        cfg = _LIST_CFG["bank_tcfd"]
    ca, pa = _asset_map(cp, cfg), _asset_map(pp, cfg)
    levC, levP = stated_level(cp), stated_level(pp)
    totC = sum(a["value_eur"] for a in ca.values())
    varC = None if levC is None else sum(a["value_eur"] for a in ca.values() if _at(a, levC))
    totP = sum(a["value_eur"] for a in pa.values())
    varP = None if levP is None else sum(a["value_eur"] for a in pa.values() if _at(a, levP))

    # per-hazard exposure shift
    ch, ph = cp.get("by_hazard") or {}, pp.get("by_hazard") or {}
    hazards = sorted(set(ch) | set(ph),
                     key=lambda h: -abs((ch.get(h, {}).get("exposed_value_eur", 0) or 0)
                                        - (ph.get(h, {}).get("exposed_value_eur", 0) or 0)))
    by_hazard = [{"hazard": h, **_delta(ch[h]["exposed_value_eur"] if h in ch else 0,
                                        ph[h]["exposed_value_eur"] if h in ph else 0)} for h in hazards]

    # drivers
    new_at_risk, left_at_risk, movers = [], [], []
    both = levC is not None and levP is not None
    for aid, a in ca.items():
        p = pa.get(aid)
        now_risk, was_risk = _at(a, levC), _at(p, levP)
        if both and now_risk and not was_risk:
            new_at_risk.append({"asset": a["name"], "value_eur": a["value_eur"], "score": a["score"], "bucket": a["bucket"]})
        if p and a["score"] is not None and p["score"] is not None and a["score"] != p["score"]:
            movers.append({"asset": a["name"], "value_eur": a["value_eur"],
                           "from_score": p["score"], "to_score": a["score"],
                           "delta": round(a["score"] - p["score"], 1),
                           "from_bucket": p["bucket"], "to_bucket": a["bucket"]})
    for aid, p in pa.items():
        a = ca.get(aid)
        was_risk, now_risk = _at(p, levP), _at(a, levC)
        if both and was_risk and not now_risk:
            left_at_risk.append({"asset": p["name"], "value_eur": p["value_eur"],
                                 "score": (a or p)["score"], "bucket": (a or p)["bucket"], "gone": a is None})

    new_at_risk.sort(key=lambda x: -(x["value_eur"] or 0))
    left_at_risk.sort(key=lambda x: -(x["value_eur"] or 0))
    movers.sort(key=lambda x: -abs((x["delta"] or 0) * (x["value_eur"] or 0)))

    pctC = None if varC is None else round(100 * varC / totC, 1) if totC else 0
    pctP = None if varP is None else round(100 * varP / totP, 1) if totP else 0
    return {
        "headline": {
            "total_value": _delta(totC, totP),
            "value_at_risk": _delta(varC, varP),
            "pct_at_risk": {"now": pctC, "prior": pctP,
                            "delta": None if pctC is None or pctP is None else round(pctC - pctP, 1)},
        },
        "at_risk_level": {"now": levC, "prior": levP, "changed": levC != levP,
                          **({"gap": "not stated: method.at_risk_level"} if not both else {})},
        "by_hazard": by_hazard,
        "drivers": {"new_at_risk": new_at_risk[:8], "left_at_risk": left_at_risk[:8], "movers": movers[:8]},
        "counts": {"assets_now": len(ca), "assets_prior": len(pa),
                   "added": len(set(ca) - set(pa)), "removed": len(set(pa) - set(ca))},
    }
