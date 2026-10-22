"""Risk decisions — the 'Act' step. Two signals raise an exposure to decide on, through one lifecycle (the sector's
verb-pack, the organisation's 4-eyes rule, its playbook):

  crossing   the exposures that CROSS from below the institution's stated at-risk level today (method.at_risk_level)
             to at or above it by a chosen scenario/horizon — the projection the forward-risk brief uses
             (v_portfolio_entity_physical_risk; `heat_acute` excluded from the headline, the portfolio convention)
  loss       the assets whose tested yearly loss is at or above the share of their value the institution states
             (method.loss_signal_share), today's climate — services.loss.signals (the decisions of 2026-10-22)

An officer records a decision on each with a rationale. The risk_decision table is the audit trail; the latest row by
sequence per (signal, entity, scenario, horizon) is the standing call. What a 'monitor' decision opens is
services.intelligence.decision_watch.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

# ── Sector verb-packs — the ONLY sector-specific part of the decision engine ──────────────────────────────
# The subject (dial 1) and the action vocabulary (dial 2) vary by sector; the lifecycle, playbook automation,
# 4-eyes and task spin-off are identical across every vertical. Every pack shares the tail engage/disclose/
# monitor/accept.
_SHARED = ("engage", "disclose", "monitor", "accept")
SECTOR_ACTIONS: dict[str, tuple[str, ...]] = {
    "banking":    ("reprice", "adjust_terms", "limit_exit", "provision") + _SHARED,
    "insurance":  ("reprice", "adjust_cover", "exclude", "non_renew", "reinsure") + _SHARED,
    "assetmgmt":  ("reweight", "engage_issuer", "divest", "hedge") + _SHARED,
    "realestate": ("adaptation_capex", "reposition", "dispose", "insure") + _SHARED,
    "agri":       ("reallocate_origin", "diversify_supplier", "buffer_prebuy", "adaptation_invest", "renegotiate") + _SHARED,
}
ACTIONS = SECTOR_ACTIONS["banking"]                                          # legacy alias (bank default)
ALL_ACTIONS = tuple(sorted({a for acts in SECTOR_ACTIONS.values() for a in acts}))


def actions_for(vertical: str) -> tuple[str, ...]:
    """The decision verb-pack for a sector — sent to the UI so it offers the right actions."""
    return SECTOR_ACTIONS.get(vertical, SECTOR_ACTIONS["banking"])


# actions that imply follow-up work → a card is spun on the Kanban board when the decision is approved
ACTIONABLE = {"engage", "reprice", "disclose"} | {
    a for v, acts in SECTOR_ACTIONS.items() for a in acts if a not in ("monitor", "accept")}
_TASK_TITLE = {
    "engage": "Engage counterparty", "reprice": "Reprice at renewal", "disclose": "Disclose climate risk",
    "adjust_terms": "Adjust terms / covenant", "limit_exit": "Limit or exit exposure", "provision": "Review provisioning",
    "adjust_cover": "Adjust deductible / limit", "exclude": "Add exclusion", "non_renew": "Non-renew at expiry", "reinsure": "Review reinsurance",
    "reweight": "Reweight holding", "engage_issuer": "Engage issuer", "divest": "Divest holding", "hedge": "Hedge exposure",
    "adaptation_capex": "Plan adaptation capex", "reposition": "Reposition asset", "dispose": "Dispose asset", "insure": "Insure asset",
    "reallocate_origin": "Reallocate sourcing origin", "diversify_supplier": "Diversify supplier",
    "buffer_prebuy": "Build buffer / pre-buy", "adaptation_invest": "Invest in supplier adaptation", "renegotiate": "Renegotiate contract",
}
ACTION_LABELS = {**_TASK_TITLE, "monitor": "Monitor / watchlist", "accept": "Accept risk"}
SUBJECT_NOUN = {"banking": "exposure", "insurance": "policy", "assetmgmt": "holding",
                "realestate": "property", "agri": "commodity"}
VERTICAL = {"bank": "banking", "asset_manager": "assetmgmt", "insurer": "insurance", "reit": "realestate",
            "manufacturer": "agri"}
SIGNALS = ("crossing", "loss")
TODAY = ("baseline", "current")      # a loss signal is on today's climate


class DecisionError(ValueError):
    pass


def crossings(session: Session, org_id: str, vertical: str, scenario: str, horizon: str, at_risk: float) -> list[dict]:
    """Subjects newly crossing the stated at-risk level by (scenario, horizon): worst priceable hazard today < level,
    at the horizon ≥ level. Ranked by adverse migration × value. Each carries its latest standing decision (if any).
    The subject is the financial entity (FIN) or the sourcing commodity/origin (agri) — same shape, same
    lifecycle. Dial 1 of the standardized decision layer."""
    if horizon not in ("2030", "2050", "2100"):
        raise DecisionError("horizon must be 2030 / 2050 / 2100")
    if vertical == "agri":
        return _agri_crossings(session, org_id, scenario, horizon, at_risk)
    rows = session.execute(text("""
        WITH cur AS (
            SELECT DISTINCT ON (v.entity_id) v.entity_id, v.physical_risk_score AS sc
            FROM v_portfolio_entity_physical_risk v
            WHERE v.org_id = :o AND v.vertical = :vert AND v.headline_eligible
              AND v.scenario = 'baseline' AND v.time_horizon = 'current'
            ORDER BY v.entity_id, v.physical_risk_score DESC
        ), fut AS (
            SELECT DISTINCT ON (v.entity_id) v.entity_id, v.physical_risk_score AS sc, v.hazard_type AS driver
            FROM v_portfolio_entity_physical_risk v
            WHERE v.org_id = :o AND v.vertical = :vert AND v.headline_eligible
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


def _agri_crossings(session: Session, org_id: str, scenario: str, horizon: str, at_risk: float) -> list[dict]:
    """Agri subject = the sourced COMMODITY (commodity_id, a uuid — fits the same entity-keyed lifecycle).
    A commodity crosses when its worst plot hazard rises from < line today to ≥ line at the horizon; value is
    the commodity's annual sourcing spend. The recommendation source downstream is the re-sourcing engine."""
    rows = session.execute(text("""
        WITH cur AS (
            SELECT commodity_id, MAX(physical_risk_score) AS sc
            FROM v_sc_plot_physical_risk
            WHERE org_id = :o AND scenario = 'baseline' AND time_horizon = 'current' AND hazard_type <> 'heat_acute'
            GROUP BY commodity_id
        ), fut AS (
            SELECT DISTINCT ON (commodity_id) commodity_id, physical_risk_score AS sc, hazard_type AS driver
            FROM v_sc_plot_physical_risk
            WHERE org_id = :o AND scenario = :scen AND time_horizon = :hz AND hazard_type <> 'heat_acute'
            ORDER BY commodity_id, physical_risk_score DESC
        ), spend AS (
            SELECT commodity_id, SUM(CAST(annual_spend_eur AS FLOAT)) AS val
            FROM sc_sourcing_plots WHERE org_id = :o GROUP BY commodity_id
        )
        SELECT co.commodity_id::text AS eid, co.name AS entity_name, COALESCE(spend.val, 0) AS val,
               cur.sc AS cur_sc, fut.sc AS fut_sc, fut.driver
        FROM fut
        JOIN sc_commodities co ON co.commodity_id = fut.commodity_id
        LEFT JOIN cur ON cur.commodity_id = fut.commodity_id
        LEFT JOIN spend ON spend.commodity_id = fut.commodity_id
        WHERE (cur.sc IS NULL OR cur.sc < :ar) AND fut.sc >= :ar
    """), {"o": org_id, "scen": scenario, "hz": horizon, "ar": at_risk}).mappings().all()
    live = _live_decisions(session, org_id, scenario, horizon)
    out = []
    for r in rows:
        cur_sc = r["cur_sc"]
        out.append({
            "entity_id": r["eid"], "entity_name": r["entity_name"], "value_eur": r["val"] or 0.0,
            "country": None, "region": None, "driver": r["driver"],
            "current_score": round(cur_sc, 1) if cur_sc is not None else None,
            "future_score": round(r["fut_sc"], 1) if r["fut_sc"] is not None else None,
            "delta": round((r["fut_sc"] or 0) - (cur_sc or 0), 1),
            "decision": live.get(r["eid"]),
        })
    out.sort(key=lambda x: -(max(0.0, x["delta"]) * (x["value_eur"] or 0)))
    return out


def _live_decisions(session: Session, org_id: str, scenario: str, horizon: str, signal: str = "crossing") -> dict:
    """The latest decision (by sequence) per entity for this signal, scenario and horizon, whatever its 4-eyes status —
    a 'proposed' one still shows as pending so it isn't re-proposed; 'approved' is the standing call."""
    rows = session.execute(text("""
        SELECT DISTINCT ON (d.entity_id) d.entity_id::text AS eid, d.action, d.rationale, d.status,
               d.decided_at, mu.email AS by, cu.email AS checker
        FROM risk_decision d
        LEFT JOIN users mu ON mu.user_id = d.decided_by
        LEFT JOIN users cu ON cu.user_id = d.decided_by_checker
        WHERE d.org_id = :o AND d.signal = :sig AND d.scenario = :s AND d.horizon = :h
          AND d.status NOT IN ('rejected', 'withdrawn')
        ORDER BY d.entity_id, d.seq DESC
    """), {"o": org_id, "sig": signal, "s": scenario, "h": horizon}).mappings().all()
    return {r["eid"]: {"action": r["action"], "rationale": r["rationale"], "status": r["status"],
                       "by": r["by"], "checker": r["checker"], "at": r["decided_at"].isoformat()} for r in rows}


def loss_signals(session: Session, org_id: str, method) -> dict:
    """The assets the tested-loss signal raises (services.loss.signals.signals), each with its standing decision."""
    from services.loss.signals import signals
    out = signals(session, org_id, method)
    live = _live_decisions(session, org_id, *TODAY, signal="loss")
    return {**out, "signals": [{**s, "decision": live.get(s["entity_id"])} for s in out["signals"]]}


_PLAYBOOK_FIELDS = ("spin_task", "assignee_user_id", "due_days", "notify", "flag_disclosure", "watchlist", "webhook")


def playbook(session: Session, org_id: str) -> dict:
    """The org's effective decision playbook (its rows over the platform defaults), keyed by action → the
    automations to run when that decision is approved."""
    rows = session.execute(text("""
        SELECT DISTINCT ON (action) action, spin_task, assignee_user_id::text AS assignee_user_id, due_days,
               notify, flag_disclosure, watchlist, webhook, (org_id IS NOT NULL) AS org_override
        FROM decision_playbook WHERE org_id = :o OR org_id IS NULL
        ORDER BY action, org_id NULLS LAST
    """), {"o": org_id}).mappings().all()
    return {r["action"]: dict(r) for r in rows}


def set_playbook(session: Session, org_id: str, actor: str, action: str, patch: dict) -> dict:
    """Upsert the org's row for one action. Only known automation fields are written."""
    if action not in ALL_ACTIONS:
        raise DecisionError(f"unknown action '{action}'")
    cur = playbook(session, org_id).get(action, {})
    merged = {f: patch.get(f, cur.get(f)) for f in _PLAYBOOK_FIELDS}
    session.execute(text("""
        INSERT INTO decision_playbook (org_id, action, spin_task, assignee_user_id, due_days, notify,
                                       flag_disclosure, watchlist, webhook, updated_by, updated_at)
        VALUES (:o, :a, :spin, CAST(:asg AS uuid), :due, :notify, :flag, :watch, :hook, :u, now())
        ON CONFLICT (org_id, action) WHERE org_id IS NOT NULL
        DO UPDATE SET spin_task=EXCLUDED.spin_task, assignee_user_id=EXCLUDED.assignee_user_id,
                      due_days=EXCLUDED.due_days, notify=EXCLUDED.notify, flag_disclosure=EXCLUDED.flag_disclosure,
                      watchlist=EXCLUDED.watchlist, webhook=EXCLUDED.webhook, updated_by=EXCLUDED.updated_by, updated_at=now()
    """), {"o": org_id, "a": action, "spin": bool(merged["spin_task"]),
           "asg": merged["assignee_user_id"] or None, "due": merged["due_days"],
           "notify": bool(merged["notify"]), "flag": bool(merged["flag_disclosure"]),
           "watch": bool(merged["watchlist"]), "hook": bool(merged["webhook"]), "u": actor})
    return playbook(session, org_id).get(action, {})


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


def _run_playbook(session: Session, org_id: str, actor: str, did, action: str, *, entity_id: str | None,
                  entity_name: str | None, scenario: str | None, horizon: str | None, rationale: str | None,
                  signal: str = "crossing"):
    """Run the org's configured automations for a CONFIRMED decision — a Kanban card (auto-assigned + due),
    a notification to the owner, and/or a webhook to the customer's endpoints. Off unless the playbook enables
    them. Each is best-effort so one failing automation never rolls back the approval."""
    pb = playbook(session, org_id).get(action, {})
    label = _TASK_TITLE.get(action, action.title())
    task = None
    if pb.get("spin_task"):
        from services.governance.tasks import create_task
        due = None
        if pb.get("due_days") is not None:
            due = session.execute(text("SELECT (CURRENT_DATE + (:d || ' days')::interval)::date"),
                                  {"d": int(pb["due_days"])}).scalar().isoformat()
        title = f"{label} — {entity_name or 'exposure'}"
        desc = ((f"Tested-loss decision ({action}): its tested yearly loss is at or above your loss signal level. "
                 if signal == "loss" else f"Forward-risk decision ({action}) under {scenario} · by {horizon}. ")
                + (rationale or ""))
        task = create_task(session, org_id, actor, title=title, description=desc.strip(), criticality="high",
                           assignee_user_id=pb.get("assignee_user_id"), due_date=due,
                           source="decision", source_ref=f"decision:{did}")
    if pb.get("notify") and task and task.get("assignee_email"):
        try:
            from core.config import settings
            from services.notifications import mailer
            link = f"{settings.APP_BASE_URL}/tasks?task={task['task_id']}"
            kind = "tested-loss decision" if signal == "loss" else "forward-risk decision"
            oid = mailer.queue_email(session, org_id=org_id, to_email=task["assignee_email"],
                                     subject=f"{label} · {entity_name or 'exposure'} — {kind}",
                                     html=f'<p>A {kind} (<b>{action}</b>) on “{entity_name}” was approved and assigned to you.</p><p><a href="{link}">Open the task →</a></p>',
                                     text_body=f"A {kind} ({action}) on {entity_name} was approved and assigned to you.\nOpen: {link}\n",
                                     kind="decision", ref_type="decision", ref_id=str(did))
            if oid:
                mailer.dispatch(session)
        except Exception:
            pass
    if pb.get("watchlist") and entity_id:
        # put the exposure on a watchlist with a re-review date; the scheduled re-check measures it the way its
        # signal does and escalates if it worsens further (services.intelligence.decision_watch)
        from services.intelligence.decision_watch import WATCH_REVIEW_DAYS, open_watch
        review_days = int(pb["due_days"]) if pb.get("due_days") is not None else WATCH_REVIEW_DAYS
        open_watch(session, org_id, actor, did, signal=signal, entity_id=entity_id, entity_name=entity_name,
                   scenario=scenario, horizon=horizon, review_days=review_days)
    if pb.get("flag_disclosure") and entity_id:
        # flag the exposure for the next climate filing — the reporting team sees it in the cockpit
        session.execute(text("""
            INSERT INTO decision_disclosure_flag (org_id, entity_id, entity_name, scenario, horizon, decision_id,
                                                  signal, flagged_by)
            VALUES (:o, CAST(:e AS uuid), :n, :s, :h, CAST(:d AS uuid), :sig, :u)
            ON CONFLICT (org_id, entity_id, signal) WHERE status = 'open' DO NOTHING
        """), {"o": org_id, "e": entity_id, "n": entity_name, "s": scenario, "h": horizon, "d": did, "sig": signal,
               "u": actor})
        # connect/push: a raised disclosure flag is a real, discrete moment the reporting team's tooling wants
        try:
            from services.integrations.webhooks import emit_event
            emit_event(session, org_id, "disclosure.flag_raised", {
                "decision_id": str(did), "entity_id": entity_id, "entity_name": entity_name,
                "signal": signal, "scenario": scenario, "horizon": horizon,
            })
        except Exception:
            pass
    if pb.get("webhook"):
        try:
            from services.integrations.webhooks import emit_event
            emit_event(session, org_id, "risk.decision.approved", {
                "decision_id": str(did), "action": action, "entity_id": entity_id,
                "entity_name": entity_name, "signal": signal, "scenario": scenario, "horizon": horizon,
            })
        except Exception:
            pass
    return task


def disclosure_flags(session: Session, org_id: str) -> list[dict]:
    """Exposures flagged (by an approved 'disclose' decision) for the next climate filing — the Act→Report bridge."""
    rows = session.execute(text("""
        SELECT f.flag_id::text AS flag_id, f.entity_name, f.signal, f.scenario, f.horizon, f.flagged_at, u.email AS by
        FROM decision_disclosure_flag f LEFT JOIN users u ON u.user_id = f.flagged_by
        WHERE f.org_id = :o AND f.status = 'open' ORDER BY f.flagged_at DESC, f.flag_id
    """), {"o": org_id}).mappings().all()
    return [{"flag_id": r["flag_id"], "entity_name": r["entity_name"], "signal": r["signal"], "scenario": r["scenario"],
             "horizon": r["horizon"], "by": r["by"], "at": r["flagged_at"].isoformat()} for r in rows]


def resolve_disclosure_flag(session: Session, org_id: str, flag_id: str, actor: str, status: str = "included") -> None:
    if status not in ("included", "dismissed"):
        raise DecisionError("status must be 'included' or 'dismissed'")
    session.execute(text("""
        UPDATE decision_disclosure_flag SET status = :s, resolved_by = :u, resolved_at = now()
        WHERE org_id = :o AND flag_id = CAST(:f AS uuid) AND status = 'open'
    """), {"s": status, "u": actor, "o": org_id, "f": flag_id})


def decide(session: Session, org_id: str, actor: str, *, entity_id: str, entity_name: str | None,
           scenario: str | None, horizon: str | None, action: str, rationale: str | None,
           value_eur: float | None = None, signal: str = "crossing") -> dict:
    """Record a decision on what a signal raised (SIGNALS; a loss signal is on today's climate, whatever scenario and
    horizon are passed). Whether it needs a second approval (4-eyes) is the ORG's choice, set at onboarding through
    the approval matrix — off by default. If 4-eyes doesn't apply, the decision is approved on the spot and any
    Kanban card is spun immediately; otherwise it stays 'proposed' until a checker approves it."""
    if action not in ALL_ACTIONS:
        raise DecisionError(f"action must be one of {ALL_ACTIONS}")
    if signal == "loss":
        scenario, horizon = TODAY
    rationale = (rationale or "").strip() or None
    needs = _needs_four_eyes(session, org_id, value_eur)
    status = "proposed" if needs else "approved"
    did = session.execute(text("""
        INSERT INTO risk_decision (org_id, entity_id, entity_name, signal, scenario, horizon, action, rationale, status,
                                   decided_by, confirmed_at)
        VALUES (:o, CAST(:e AS uuid), :n, :sig, :s, :h, :a, :r, :st, :u, CASE WHEN :st = 'approved' THEN now() END)
        RETURNING decision_id
    """), {"o": org_id, "e": entity_id, "n": entity_name, "sig": signal, "s": scenario, "h": horizon,
           "a": action, "r": rationale, "st": status, "u": actor}).scalar()

    if not needs:
        # approved by policy (no second approval required) — run the playbook now
        task = _run_playbook(session, org_id, actor, did, action, entity_id=entity_id, entity_name=entity_name,
                             scenario=scenario, horizon=horizon, rationale=rationale, signal=signal)
        return {"decision_id": str(did), "action": action, "status": "approved",
                "task_id": task.get("task_id") if task else None}

    # 4-eyes required → raise the shared approval request (checker ≠ maker enforced by the approvals router)
    import json
    payload = {"decision_id": str(did), "entity_id": entity_id, "entity_name": entity_name, "signal": signal,
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
        task = _run_playbook(session, org_id, actor, did, p.get("action"), entity_id=p.get("entity_id"),
                             entity_name=p.get("entity_name"), scenario=p.get("scenario"),
                             horizon=p.get("horizon"), rationale=p.get("rationale"),
                             signal=p.get("signal") or "crossing")      # requests raised before signals: crossings
    return {"decision_id": did, "status": status, "task_id": task.get("task_id") if task else None}


def decisions_log(session: Session, org_id: str, limit: int = 100) -> list[dict]:
    rows = session.execute(text("""
        SELECT d.entity_name, d.signal, d.scenario, d.horizon, d.action, d.rationale, d.status, d.decided_at,
               u.email AS by
        FROM risk_decision d LEFT JOIN users u ON u.user_id = d.decided_by
        WHERE d.org_id = :o ORDER BY d.seq DESC LIMIT :n
    """), {"o": org_id, "n": limit}).mappings().all()
    return [{"entity_name": r["entity_name"], "signal": r["signal"], "scenario": r["scenario"], "horizon": r["horizon"],
             "action": r["action"], "rationale": r["rationale"], "status": r["status"],
             "by": r["by"], "at": r["decided_at"].isoformat()} for r in rows]
