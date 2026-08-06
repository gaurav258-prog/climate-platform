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
# actions that imply follow-up work → a card is spun on the Kanban board when the decision is approved
ACTIONABLE = {"engage", "reprice", "disclose"}
_TASK_TITLE = {"engage": "Engage counterparty", "reprice": "Reprice at renewal", "disclose": "Disclose climate risk"}
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
    """The latest decision per entity for this (scenario, horizon), whatever its 4-eyes status — a 'proposed'
    one still shows as pending so it isn't re-proposed; 'approved' is the standing call."""
    rows = session.execute(text("""
        SELECT DISTINCT ON (d.entity_id) d.entity_id::text AS eid, d.action, d.rationale, d.status,
               d.decided_at, mu.email AS by, cu.email AS checker
        FROM risk_decision d
        LEFT JOIN users mu ON mu.user_id = d.decided_by
        LEFT JOIN users cu ON cu.user_id = d.decided_by_checker
        WHERE d.org_id = :o AND d.scenario = :s AND d.horizon = :h AND d.status <> 'rejected'
        ORDER BY d.entity_id, d.decided_at DESC
    """), {"o": org_id, "s": scenario, "h": horizon}).mappings().all()
    return {r["eid"]: {"action": r["action"], "rationale": r["rationale"], "status": r["status"],
                       "by": r["by"], "checker": r["checker"], "at": r["decided_at"].isoformat()} for r in rows}


def decision_policy(session: Session, org_id: str) -> dict:
    """The org's 4-eyes rule for forward-risk decisions (its own row over the platform default). Onboarding-
    configurable via the approval matrix. requires_approval + an optional value threshold_eur."""
    row = session.execute(text("""
        SELECT requires_approval, threshold_eur FROM approval_policy
        WHERE action_key = 'risk.decision' AND (org_id = :o OR org_id IS NULL)
        ORDER BY org_id NULLS LAST LIMIT 1
    """), {"o": org_id}).mappings().first()
    if not row:
        return {"requires_approval": False, "threshold_eur": None}
    return {"requires_approval": bool(row["requires_approval"]),
            "threshold_eur": float(row["threshold_eur"]) if row["threshold_eur"] is not None else None}


def _needs_four_eyes(session: Session, org_id: str, value_eur: float | None) -> bool:
    pol = decision_policy(session, org_id)
    if not pol["requires_approval"]:
        return False                                  # customer hasn't turned it on
    if pol["threshold_eur"] is None:
        return True                                   # on, no threshold → every decision
    return (value_eur or 0) >= pol["threshold_eur"]   # on, threshold → only above the line


def _spin_task(session: Session, org_id: str, actor: str, decision_id, action: str,
               entity_name: str | None, scenario: str | None, horizon: str | None, rationale: str | None):
    """Spin the Kanban card for an actionable, confirmed decision (engage / reprice / disclose)."""
    if action not in ACTIONABLE:
        return None
    from services.governance.tasks import create_task
    title = f"{_TASK_TITLE.get(action, action.title())} — {entity_name or 'exposure'}"
    desc = f"Forward-risk decision ({action}) under {scenario} · by {horizon}. " + (rationale or "")
    return create_task(session, org_id, actor, title=title, description=desc.strip(), criticality="high",
                       source="decision", source_ref=f"decision:{decision_id}")


def decide(session: Session, org_id: str, actor: str, *, entity_id: str, entity_name: str | None,
           scenario: str, horizon: str, action: str, rationale: str | None, value_eur: float | None = None) -> dict:
    """Record a decision. Whether it needs a second approval (4-eyes) is the ORG's choice, set at onboarding
    through the approval matrix — off by default. If 4-eyes doesn't apply, the decision is approved on the spot
    and any Kanban card is spun immediately; otherwise it stays 'proposed' until a checker approves it."""
    if action not in ACTIONS:
        raise DecisionError(f"action must be one of {ACTIONS}")
    rationale = (rationale or "").strip() or None
    needs = _needs_four_eyes(session, org_id, value_eur)
    status = "proposed" if needs else "approved"
    did = session.execute(text("""
        INSERT INTO risk_decision (org_id, entity_id, entity_name, scenario, horizon, action, rationale, status, decided_by,
                                   confirmed_at)
        VALUES (:o, CAST(:e AS uuid), :n, :s, :h, :a, :r, :st, :u, CASE WHEN :st = 'approved' THEN now() END)
        RETURNING decision_id
    """), {"o": org_id, "e": entity_id, "n": entity_name, "s": scenario, "h": horizon,
           "a": action, "r": rationale, "st": status, "u": actor}).scalar()

    if not needs:
        # approved by policy (no second approval required) — spin the card now
        task = _spin_task(session, org_id, actor, did, action, entity_name, scenario, horizon, rationale)
        return {"decision_id": str(did), "action": action, "status": "approved",
                "task_id": task.get("task_id") if task else None}

    # 4-eyes required → raise the shared approval request (checker ≠ maker enforced by the approvals router)
    import json
    payload = {"decision_id": str(did), "entity_id": entity_id, "entity_name": entity_name,
               "scenario": scenario, "horizon": horizon, "action": action, "rationale": rationale}
    label = _TASK_TITLE.get(action, action.title())
    rid = session.execute(text("""
        INSERT INTO approval_requests (org_id, request_type, title, payload, maker_user_id)
        VALUES (:o, 'risk.decision', :ti, CAST(:p AS jsonb), :m) RETURNING request_id
    """), {"o": org_id, "ti": f"{label} · {entity_name or 'exposure'}", "p": json.dumps(payload), "m": actor}).scalar()
    session.execute(text("UPDATE risk_decision SET approval_request_id = :r WHERE decision_id = :d"),
                    {"r": rid, "d": did})
    return {"decision_id": str(did), "action": action, "status": "proposed", "approval_request_id": str(rid)}


def apply_decision(session: Session, org_id: str, payload: dict, decision: str, actor: str) -> dict:
    """Called from the approvals decide handler when a risk.decision request is decided. On approval the
    decision becomes the standing call, and an actionable one spins a card on the Kanban board."""
    did = (payload or {}).get("decision_id")
    status = "approved" if decision == "approved" else "rejected"
    session.execute(text("""
        UPDATE risk_decision SET status = :s, decided_by_checker = :c, confirmed_at = now()
        WHERE decision_id = :d AND org_id = :o AND status = 'proposed'
    """), {"s": status, "c": actor, "d": did, "o": org_id})
    task = None
    if status == "approved":
        p = payload or {}
        task = _spin_task(session, org_id, actor, did, p.get("action"), p.get("entity_name"),
                          p.get("scenario"), p.get("horizon"), p.get("rationale"))
    return {"decision_id": did, "status": status, "task_id": task.get("task_id") if task else None}


def decisions_log(session: Session, org_id: str, limit: int = 100) -> list[dict]:
    rows = session.execute(text("""
        SELECT d.entity_name, d.scenario, d.horizon, d.action, d.rationale, d.status, d.decided_at, u.email AS by
        FROM risk_decision d LEFT JOIN users u ON u.user_id = d.decided_by
        WHERE d.org_id = :o ORDER BY d.decided_at DESC LIMIT :n
    """), {"o": org_id, "n": limit}).mappings().all()
    return [{"entity_name": r["entity_name"], "scenario": r["scenario"], "horizon": r["horizon"],
             "action": r["action"], "rationale": r["rationale"], "status": r["status"],
             "by": r["by"], "at": r["decided_at"].isoformat()} for r in rows]
