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

_AT_RISK = ("H", "VH")


def _asset_map(payload: dict, cfg: dict) -> dict:
    out = {}
    for a in payload.get(cfg["list"]) or []:
        out[a.get(cfg["id"])] = {
            "name": a.get(cfg["name"]), "value_eur": a.get(cfg["value"]) or 0,
            "score": a.get("headline_score"), "bucket": a.get("headline_bucket"),
        }
    return out


def _delta(now, prior):
    now = now or 0
    prior = prior or 0
    return {"now": round(now), "prior": round(prior), "delta": round(now - prior)}


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
    return {
        "supported": True, "filing_id": filing_id, "prior_filing_id": prior_id, "framework": cur["framework"],
        "basis": {"current": {"period": cur["period_label"], **(cur.get("snapshot") or {}).get("reporting_basis", {})},
                  "prior": {"period": prior["period_label"], **(prior.get("snapshot") or {}).get("reporting_basis", {})}},
        **decompose(cp, pp, cfg),
    }


def decompose(cp: dict, pp: dict, cfg: dict | None = None) -> dict:
    """Pure decomposition of a current vs prior located-book payload — headline shifts, per-hazard exposure
    shifts, and the entities driving them. Total & value-at-risk are computed from the entity list (so it's
    sector-agnostic: loan book / property book / underwriting book). No DB, so it's unit-testable."""
    if cfg is None:   # default to the loan-book shape (keeps existing callers/tests working)
        from services.governance.filing_lineage import _LIST_CFG
        cfg = _LIST_CFG["bank_tcfd"]
    ca, pa = _asset_map(cp, cfg), _asset_map(pp, cfg)
    totC = sum(a["value_eur"] for a in ca.values())
    varC = sum(a["value_eur"] for a in ca.values() if a["bucket"] in _AT_RISK)
    totP = sum(a["value_eur"] for a in pa.values())
    varP = sum(a["value_eur"] for a in pa.values() if a["bucket"] in _AT_RISK)

    # per-hazard exposure shift
    ch, ph = cp.get("by_hazard") or {}, pp.get("by_hazard") or {}
    hazards = sorted(set(ch) | set(ph),
                     key=lambda h: -abs((ch.get(h, {}).get("exposed_value_eur", 0) or 0)
                                        - (ph.get(h, {}).get("exposed_value_eur", 0) or 0)))
    by_hazard = [{"hazard": h, **_delta(ch.get(h, {}).get("exposed_value_eur"),
                                        ph.get(h, {}).get("exposed_value_eur"))} for h in hazards]

    # drivers
    new_at_risk, left_at_risk, movers = [], [], []
    for aid, a in ca.items():
        p = pa.get(aid)
        now_risk = a["bucket"] in _AT_RISK
        was_risk = bool(p) and p["bucket"] in _AT_RISK
        if now_risk and not was_risk:
            new_at_risk.append({"asset": a["name"], "value_eur": a["value_eur"], "score": a["score"], "bucket": a["bucket"]})
        if p and a["score"] is not None and p["score"] is not None and a["score"] != p["score"]:
            movers.append({"asset": a["name"], "value_eur": a["value_eur"],
                           "from_score": p["score"], "to_score": a["score"],
                           "delta": round(a["score"] - p["score"], 1),
                           "from_bucket": p["bucket"], "to_bucket": a["bucket"]})
    for aid, p in pa.items():
        a = ca.get(aid)
        was_risk = p["bucket"] in _AT_RISK
        now_risk = bool(a) and a["bucket"] in _AT_RISK
        if was_risk and not now_risk:
            left_at_risk.append({"asset": p["name"], "value_eur": p["value_eur"],
                                 "score": (a or p)["score"], "bucket": (a or p)["bucket"], "gone": a is None})

    new_at_risk.sort(key=lambda x: -(x["value_eur"] or 0))
    left_at_risk.sort(key=lambda x: -(x["value_eur"] or 0))
    movers.sort(key=lambda x: -abs((x["delta"] or 0) * (x["value_eur"] or 0)))

    pctC = round(100 * varC / totC, 1) if totC else 0
    pctP = round(100 * varP / totP, 1) if totP else 0
    return {
        "headline": {
            "total_value": _delta(totC, totP),
            "value_at_risk": _delta(varC, varP),
            "pct_at_risk": {"now": pctC, "prior": pctP, "delta": round(pctC - pctP, 1)},
        },
        "by_hazard": by_hazard,
        "drivers": {"new_at_risk": new_at_risk[:8], "left_at_risk": left_at_risk[:8], "movers": movers[:8]},
        "counts": {"assets_now": len(ca), "assets_prior": len(pa),
                   "added": len(set(ca) - set(pa)), "removed": len(set(pa) - set(ca))},
    }
