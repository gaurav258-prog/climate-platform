"""
Insurance underwriting — public read-only endpoints for the Loss-curve pricing
workspace.

Projects the golden source (canonical_scores) onto an insurer's property book
by H3 cell (v_insurance_policy_physical_risk), then runs each policy through
ml/scoring/insurance_pricing.py's score -> scenario loss -> expected annual
loss -> premium chain. Mirrors bank.py/supply.py exactly: tenant-scoped via
JWT org_id, DEMO_ORG fallback, provenance kept. Policies whose cell is
unscored return status='no_canonical_score', premium withheld -- same
governance rule as every other hazard-projected book here.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from api.deps import DbSession
from ml.scoring.insurance_pricing import price_policy

router = APIRouter(prefix="/v1/insurance", tags=["Insurance"])

DEMO_ORG = "22222222-2222-4222-8222-222222222222"  # Iberia Mutual (demo)
_bearer = HTTPBearer(auto_error=False)


def resolve_org(
    org_id: Optional[str] = Query(None),
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)] = None,
) -> str:
    """User JWT's org wins (tenant isolation); else query param; else the demo insurer."""
    token = credentials.credentials if credentials else None
    if token and not token.startswith("cp_live_"):
        from api.security import decode_access_token
        payload = decode_access_token(token)
        if payload and payload.get("org_id"):
            return payload["org_id"]
    return org_id or DEMO_ORG


OrgId = Annotated[str, Depends(resolve_org)]


def _policies_with_risk(session, org_id, scenario, horizon):
    """All of an org's policies (metadata) + their per-hazard projected risk."""
    policies = session.execute(text("""
        SELECT policy_id::text AS policy_id, policy_name, policy_type, country, region,
               CAST(latitude AS FLOAT) AS lat, CAST(longitude AS FLOAT) AS lon, h3_cell,
               CAST(sum_insured_eur AS FLOAT) AS sum_insured_eur,
               CAST(deductible_pct AS FLOAT) AS deductible_pct
        FROM insurance_policies WHERE org_id = :o ORDER BY sum_insured_eur DESC
    """), {"o": org_id}).mappings().all()

    risks = session.execute(text("""
        SELECT policy_id::text AS policy_id, hazard_type,
               physical_risk_score AS score, risk_bucket, model_version, scored_at
        FROM v_insurance_policy_physical_risk
        WHERE org_id = :o AND scenario = :s AND time_horizon = :h
    """), {"o": org_id, "s": scenario, "h": horizon}).mappings().all()

    by_policy = defaultdict(list)
    for r in risks:
        by_policy[r["policy_id"]].append({
            "hazard": r["hazard_type"], "score": round(r["score"], 1),
            "bucket": r["risk_bucket"], "model_version": r["model_version"],
            "scored_at": r["scored_at"],
        })

    out = []
    for p in policies:
        hz = sorted(by_policy.get(p["policy_id"], []), key=lambda x: -x["score"])
        headline = hz[0] if hz else None
        pricing = price_policy(headline["score"], p["sum_insured_eur"]) if headline else None
        out.append({
            **{k: p[k] for k in p.keys()},
            "hazards": hz,
            "headline_score": headline["score"] if headline else None,
            "headline_bucket": headline["bucket"] if headline else None,
            "headline_hazard": headline["hazard"] if headline else None,
            "pricing": pricing,
        })
    return out


def _rollup(policies):
    total = sum(p["sum_insured_eur"] or 0 for p in policies)
    priced = [p for p in policies if p["pricing"]]
    total_eal = sum(p["pricing"]["expected_annual_loss_eur"] for p in priced)
    total_premium = sum(p["pricing"]["gross_premium_eur"] for p in priced)
    by_bucket = defaultdict(lambda: {"count": 0, "sum_insured_eur": 0.0, "eal_eur": 0.0})
    for p in policies:
        b = p["headline_bucket"] or "none"
        by_bucket[b]["count"] += 1
        by_bucket[b]["sum_insured_eur"] += p["sum_insured_eur"] or 0
        if p["pricing"]:
            by_bucket[b]["eal_eur"] += p["pricing"]["expected_annual_loss_eur"]
    return {
        "n_policies": len(policies),
        "n_priced": len(priced),
        "total_sum_insured_eur": round(total),
        "total_expected_annual_loss_eur": round(total_eal),
        "total_gross_premium_eur": round(total_premium),
        "portfolio_loss_ratio_pct": round(100 * total_eal / total_premium, 1) if total_premium else 0,
        "by_bucket": {k: {"count": v["count"], "sum_insured_eur": round(v["sum_insured_eur"]),
                           "eal_eur": round(v["eal_eur"])} for k, v in by_bucket.items()},
        "top_policies": sorted(
            [p for p in policies if p["headline_score"] is not None],
            key=lambda p: -p["headline_score"])[:8],
    }


@router.get("/portfolio", summary="Property book projected onto the golden source")
def portfolio(session: DbSession, org_id: OrgId,
              scenario: str = Query("baseline"), horizon: str = Query("current")):
    policies = _policies_with_risk(session, org_id, scenario, horizon)
    return {"org_id": org_id, "scenario": scenario, "horizon": horizon,
            "rollup": _rollup(policies), "policies": policies}


@router.get("/summary", summary="Loss-curve pricing rollup")
def summary(session: DbSession, org_id: OrgId,
            scenario: str = Query("baseline"), horizon: str = Query("current")):
    org = session.execute(text(
        "SELECT name, type, country FROM organizations WHERE org_id = :o"
    ), {"o": org_id}).mappings().first()
    policies = _policies_with_risk(session, org_id, scenario, horizon)
    return {"org_id": org_id, "org": dict(org) if org else None, "rollup": _rollup(policies)}
