"""Forward-risk decisions — the 'Act' step. Reads the same projection the forward-risk brief uses, finds the
exposures that CROSS from below-High today into High+ by a chosen scenario/horizon, and lets an officer
record a decision on each (reprice / engage / disclose / monitor / accept) with a rationale. The
risk_decision table is the audit trail; the latest row per (entity, scenario, horizon) is the standing call.

One honest source: v_portfolio_entity_physical_risk (the same view the financial engine uses). `heat_acute`
is excluded from the headline, matching the portfolio/forward-risk convention.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

AT_RISK = 50.0                       # High+ boundary (score ≥ 50) — the decision line
ACTIONS = ("reprice", "engage", "disclose", "monitor", "accept")
VERTICAL = {"bank": "banking", "asset_manager": "assetmgmt", "insurer": "insurance", "reit": "realestate"}


class DecisionError(ValueError):
    pass


def crossings(session: Session, org_id: str, vertical: str, scenario: str, horizon: str,
              at_risk: float = AT_RISK) -> list[dict]:
    """Exposures newly crossing into High+ by (scenario, horizon): worst priceable hazard today < line, at the
    horizon ≥ line. Ranked by adverse migration × value. Each carries its latest standing decision (if any)."""
    if horizon not in ("2030", "2050", "2100"):
        raise DecisionError("horizon must be 2030 / 2050 / 2100")
    rows = session.execute(text("""
        WITH cur AS (
            SELECT DISTINCT ON (v.entity_id) v.entity_id, v.physical_risk_score AS sc
            FROM v_portfolio_entity_physical_risk v
            WHERE v.org_id = :o AND v.vertical = :vert AND v.hazard_type <> 'heat_acute'
              AND v.scenario = 'baseline' AND v.time_horizon = 'current'
            ORDER BY v.entity_id, v.physical_risk_score DESC
        ), fut AS (
            SELECT DISTINCT ON (v.entity_id) v.entity_id, v.physical_risk_score AS sc, v.hazard_type AS driver
            FROM v_portfolio_entity_physical_risk v
            WHERE v.org_id = :o AND v.vertical = :vert AND v.hazard_type <> 'heat_acute'
              AND v.scenario = :scen AND v.time_horizon = :hz
            ORDER BY v.entity_id, v.physical_risk_score DESC
        )
        SELECT e.entity_id::text AS eid, e.entity_name,
               CAST(e.primary_value_eur AS FLOAT) AS val, e.country, e.region,
               cur.sc AS cur_sc, fut.sc AS fut_sc, fut.driver
        FROM portfolio_entities e
        JOIN fut ON fut.entity_id = e.entity_id
        LEFT JOIN cur ON cur.entity_id = e.entity_id
        WHERE e.org_id = :o AND e.vertical = :vert
          AND (cur.sc IS NULL OR cur.sc < :ar) AND fut.sc >= :ar
    """), {"o": org_id, "vert": vertical, "scen": scenario, "hz": horizon, "ar": at_risk}).mappings().all()

    live = _live_decisions(session, org_id, scenario, horizon)
    out = []
    for r in rows:
        cur_sc = r["cur_sc"]
        out.append({
            "entity_id": r["eid"], "entity_name": r["entity_name"], "value_eur": r["val"] or 0.0,
            "country": r["country"], "region": r["region"], "driver": r["driver"],
            "current_score": round(cur_sc, 1) if cur_sc is not None else None,
            "future_score": round(r["fut_sc"], 1) if r["fut_sc"] is not None else None,
            "delta": round((r["fut_sc"] or 0) - (cur_sc or 0), 1),
            "decision": live.get(r["eid"]),
        })
    out.sort(key=lambda x: -(max(0.0, x["delta"]) * (x["value_eur"] or 0)))
    return out


def _live_decisions(session: Session, org_id: str, scenario: str, horizon: str) -> dict:
    rows = session.execute(text("""
        SELECT DISTINCT ON (d.entity_id) d.entity_id::text AS eid, d.action, d.rationale, d.status,
               d.decided_at, u.email AS by
        FROM risk_decision d LEFT JOIN users u ON u.user_id = d.decided_by
        WHERE d.org_id = :o AND d.scenario = :s AND d.horizon = :h
        ORDER BY d.entity_id, d.decided_at DESC
    """), {"o": org_id, "s": scenario, "h": horizon}).mappings().all()
    return {r["eid"]: {"action": r["action"], "rationale": r["rationale"], "status": r["status"],
                       "by": r["by"], "at": r["decided_at"].isoformat()} for r in rows}


def decide(session: Session, org_id: str, actor: str, *, entity_id: str, entity_name: str | None,
           scenario: str, horizon: str, action: str, rationale: str | None) -> dict:
    if action not in ACTIONS:
        raise DecisionError(f"action must be one of {ACTIONS}")
    did = session.execute(text("""
        INSERT INTO risk_decision (org_id, entity_id, entity_name, scenario, horizon, action, rationale, decided_by)
        VALUES (:o, CAST(:e AS uuid), :n, :s, :h, :a, :r, :u) RETURNING decision_id
    """), {"o": org_id, "e": entity_id, "n": entity_name, "s": scenario, "h": horizon,
           "a": action, "r": (rationale or "").strip() or None, "u": actor}).scalar()
    return {"decision_id": str(did), "action": action}


def decisions_log(session: Session, org_id: str, limit: int = 100) -> list[dict]:
    rows = session.execute(text("""
        SELECT d.entity_name, d.scenario, d.horizon, d.action, d.rationale, d.status, d.decided_at, u.email AS by
        FROM risk_decision d LEFT JOIN users u ON u.user_id = d.decided_by
        WHERE d.org_id = :o ORDER BY d.decided_at DESC LIMIT :n
    """), {"o": org_id, "n": limit}).mappings().all()
    return [{"entity_name": r["entity_name"], "scenario": r["scenario"], "horizon": r["horizon"],
             "action": r["action"], "rationale": r["rationale"], "status": r["status"],
             "by": r["by"], "at": r["decided_at"].isoformat()} for r in rows]
