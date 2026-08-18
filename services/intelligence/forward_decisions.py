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
WATCH_REVIEW_DAYS = 90               # default re-review cadence for a 'monitor' watch (overridable per playbook)
WATCH_DETERIORATION = 2.0            # score points a watched exposure must worsen by to escalate on re-check


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
    if action not in ACTIONS:
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
                  entity_name: str | None, scenario: str | None, horizon: str | None, rationale: str | None):
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
        desc = f"Forward-risk decision ({action}) under {scenario} · by {horizon}. " + (rationale or "")
        task = create_task(session, org_id, actor, title=title, description=desc.strip(), criticality="high",
                           assignee_user_id=pb.get("assignee_user_id"), due_date=due,
                           source="decision", source_ref=f"decision:{did}")
    if pb.get("notify") and task and task.get("assignee_email"):
        try:
            from services.notifications import mailer
            from core.config import settings
            link = f"{settings.APP_BASE_URL}/tasks?task={task['task_id']}"
            oid = mailer.queue_email(session, org_id=org_id, to_email=task["assignee_email"],
                                     subject=f"{label} · {entity_name or 'exposure'} — forward-risk decision",
                                     html=f'<p>A forward-risk decision (<b>{action}</b>) on “{entity_name}” was approved and assigned to you.</p><p><a href="{link}">Open the task →</a></p>',
                                     text_body=f"A forward-risk decision ({action}) on {entity_name} was approved and assigned to you.\nOpen: {link}\n",
                                     kind="decision", ref_type="decision", ref_id=str(did))
            if oid:
                mailer.dispatch(session)
        except Exception:
            pass
    if pb.get("watchlist") and entity_id:
        # put the exposure on a watchlist with a re-review date; the scheduled re-check re-scores it and
        # escalates if it deteriorates further. Baseline = the projected High+ score it was watched under.
        review_days = int(pb["due_days"]) if pb.get("due_days") is not None else WATCH_REVIEW_DAYS
        base = _projected_score(session, org_id, entity_id, scenario, horizon)
        session.execute(text("""
            INSERT INTO decision_watchlist (org_id, entity_id, entity_name, scenario, horizon, decision_id,
                                            baseline_score, review_date, added_by)
            VALUES (:o, CAST(:e AS uuid), :n, :s, :h, CAST(:d AS uuid), :base,
                    (CURRENT_DATE + (:rd || ' days')::interval)::date, :u)
            ON CONFLICT (org_id, entity_id) WHERE status = 'watching' DO NOTHING
        """), {"o": org_id, "e": entity_id, "n": entity_name, "s": scenario, "h": horizon, "d": did,
               "base": base, "rd": review_days, "u": actor})
    if pb.get("flag_disclosure") and entity_id:
        # flag the exposure for the next climate filing — the reporting team sees it in the cockpit
        session.execute(text("""
            INSERT INTO decision_disclosure_flag (org_id, entity_id, entity_name, scenario, horizon, decision_id, flagged_by)
            VALUES (:o, CAST(:e AS uuid), :n, :s, :h, CAST(:d AS uuid), :u)
            ON CONFLICT (org_id, entity_id) WHERE status = 'open' DO NOTHING
        """), {"o": org_id, "e": entity_id, "n": entity_name, "s": scenario, "h": horizon, "d": did, "u": actor})
        # connect/push: a raised disclosure flag is a real, discrete moment the reporting team's tooling wants
        try:
            from services.integrations.webhooks import emit_event
            emit_event(session, org_id, "disclosure.flag_raised", {
                "decision_id": str(did), "entity_id": entity_id, "entity_name": entity_name,
                "scenario": scenario, "horizon": horizon,
            })
        except Exception:
            pass
    if pb.get("webhook"):
        try:
            from services.integrations.webhooks import emit_event
            emit_event(session, org_id, "risk.decision.approved", {
                "decision_id": str(did), "action": action, "entity_id": entity_id,
                "entity_name": entity_name, "scenario": scenario, "horizon": horizon,
            })
        except Exception:
            pass
    return task


def disclosure_flags(session: Session, org_id: str) -> list[dict]:
    """Exposures flagged (by an approved 'disclose' decision) for the next climate filing — the Act→Report bridge."""
    rows = session.execute(text("""
        SELECT f.flag_id::text AS flag_id, f.entity_name, f.scenario, f.horizon, f.flagged_at, u.email AS by
        FROM decision_disclosure_flag f LEFT JOIN users u ON u.user_id = f.flagged_by
        WHERE f.org_id = :o AND f.status = 'open' ORDER BY f.flagged_at DESC
    """), {"o": org_id}).mappings().all()
    return [{"flag_id": r["flag_id"], "entity_name": r["entity_name"], "scenario": r["scenario"],
             "horizon": r["horizon"], "by": r["by"], "at": r["flagged_at"].isoformat()} for r in rows]


def resolve_disclosure_flag(session: Session, org_id: str, flag_id: str, actor: str, status: str = "included") -> None:
    if status not in ("included", "dismissed"):
        raise DecisionError("status must be 'included' or 'dismissed'")
    session.execute(text("""
        UPDATE decision_disclosure_flag SET status = :s, resolved_by = :u, resolved_at = now()
        WHERE org_id = :o AND flag_id = CAST(:f AS uuid) AND status = 'open'
    """), {"s": status, "u": actor, "o": org_id, "f": flag_id})


def _projected_score(session: Session, org_id: str, entity_id: str, scenario: str | None,
                     horizon: str | None) -> float | None:
    """The worst priceable-hazard physical-risk score for one exposure under (scenario, horizon) — the same
    number the crossings view ranks on (heat_acute excluded, matching the headline convention)."""
    if not scenario or not horizon:
        return None
    return session.execute(text("""
        SELECT MAX(v.physical_risk_score)
        FROM v_portfolio_entity_physical_risk v
        WHERE v.org_id = :o AND v.entity_id = CAST(:e AS uuid) AND v.hazard_type <> 'heat_acute'
          AND v.scenario = :s AND v.time_horizon = :h
    """), {"o": org_id, "e": entity_id, "s": scenario, "h": horizon}).scalar()


def watchlist(session: Session, org_id: str) -> list[dict]:
    """Open 'monitor' watches for this org — what Risk is actively watching, with the re-review date, the
    projection it was watched under, and (once re-checked) whether it has deteriorated further."""
    rows = session.execute(text("""
        SELECT w.watch_id::text AS watch_id, w.entity_name, w.scenario, w.horizon, w.baseline_score,
               w.review_date, w.status, w.last_checked_at, w.last_score, w.last_delta, u.email AS by, w.added_at
        FROM decision_watchlist w LEFT JOIN users u ON u.user_id = w.added_by
        WHERE w.org_id = :o AND w.status IN ('watching','escalated')
        ORDER BY (w.status = 'escalated') DESC, COALESCE(w.last_delta, 0) DESC, w.review_date NULLS LAST
    """), {"o": org_id}).mappings().all()
    return [{"watch_id": r["watch_id"], "entity_name": r["entity_name"], "scenario": r["scenario"],
             "horizon": r["horizon"], "status": r["status"],
             "baseline_score": round(r["baseline_score"], 1) if r["baseline_score"] is not None else None,
             "last_score": round(r["last_score"], 1) if r["last_score"] is not None else None,
             "last_delta": round(r["last_delta"], 1) if r["last_delta"] is not None else None,
             "review_date": r["review_date"].isoformat() if r["review_date"] else None,
             "last_checked_at": r["last_checked_at"].isoformat() if r["last_checked_at"] else None,
             "by": r["by"], "at": r["added_at"].isoformat()} for r in rows]


def resolve_watch(session: Session, org_id: str, watch_id: str, actor: str, status: str = "cleared") -> None:
    if status not in ("cleared", "escalated"):
        raise DecisionError("status must be 'cleared' or 'escalated'")
    session.execute(text("""
        UPDATE decision_watchlist SET status = :s, resolved_by = :u, resolved_at = now()
        WHERE org_id = :o AND watch_id = CAST(:w AS uuid) AND status IN ('watching','escalated')
    """), {"s": status, "u": actor, "o": org_id, "w": watch_id})


def recheck_watchlist(session: Session, org_id: str | None = None, *, due_only: bool = False) -> list[dict]:
    """Re-score every open watch against the projection it was opened under and record the result. A watch
    that has worsened by ≥ WATCH_DETERIORATION points is ESCALATED and an alert raised (notify the watcher +
    a webhook). Returns the escalations. `due_only` (the scheduled beat) limits to watches past their review
    date; the manual trigger re-checks all. Each alert is best-effort — one failure never blocks the rest."""
    clause = "w.org_id = :o AND" if org_id else ""
    due = "AND (w.review_date IS NULL OR w.review_date <= CURRENT_DATE)" if due_only else ""
    rows = session.execute(text(f"""
        SELECT w.watch_id::text AS watch_id, w.org_id::text AS org_id, w.entity_id::text AS entity_id,
               w.entity_name, w.scenario, w.horizon, w.baseline_score, w.added_by::text AS added_by
        FROM decision_watchlist w
        WHERE {clause} w.status = 'watching' {due}
    """), {"o": org_id} if org_id else {}).mappings().all()
    escalations = []
    for w in rows:
        score = _projected_score(session, w["org_id"], w["entity_id"], w["scenario"], w["horizon"])
        base = w["baseline_score"]
        delta = (score - base) if (score is not None and base is not None) else None
        worsened = delta is not None and delta >= WATCH_DETERIORATION
        session.execute(text("""
            UPDATE decision_watchlist SET last_checked_at = now(), last_score = :sc, last_delta = :dl,
                   status = CASE WHEN :esc THEN 'escalated' ELSE status END
            WHERE watch_id = CAST(:w AS uuid)
        """), {"sc": score, "dl": delta, "esc": worsened, "w": w["watch_id"]})
        if not worsened:
            continue
        escalations.append({"watch_id": w["watch_id"], "entity_name": w["entity_name"],
                            "scenario": w["scenario"], "horizon": w["horizon"],
                            "baseline_score": round(base, 1), "score": round(score, 1), "delta": round(delta, 1)})
        _alert_deterioration(session, w, score, base, delta)
    return escalations


def _alert_deterioration(session: Session, w: dict, score: float, base: float, delta: float) -> None:
    """A watched exposure has deteriorated further — notify the watcher and fire the webhook. Best-effort."""
    try:
        from services.notifications import mailer
        email = session.execute(text("SELECT email FROM users WHERE user_id = CAST(:u AS uuid)"),
                                {"u": w["added_by"]}).scalar() if w.get("added_by") else None
        if email:
            oid = mailer.queue_email(
                session, org_id=w["org_id"], to_email=email,
                subject=f"Watchlist alert · {w['entity_name']} deteriorated further",
                html=f'<p>An exposure you are monitoring, <b>{w["entity_name"]}</b>, has deteriorated further under '
                     f'{w["scenario"]} · {w["horizon"]}: projected risk score {base:.0f} → <b>{score:.0f}</b> '
                     f'(+{delta:.0f}). It has been escalated on your watchlist.</p>',
                text_body=f"{w['entity_name']} deteriorated further under {w['scenario']} · {w['horizon']}: "
                          f"{base:.0f} → {score:.0f} (+{delta:.0f}). Escalated on your watchlist.\n",
                kind="decision", ref_type="watch", ref_id=str(w["watch_id"]))
            if oid:
                mailer.dispatch(session)
    except Exception:
        pass
    try:
        from services.integrations.webhooks import emit_event
        emit_event(session, w["org_id"], "risk.watch.deteriorated", {
            "watch_id": w["watch_id"], "entity_id": w["entity_id"], "entity_name": w["entity_name"],
            "scenario": w["scenario"], "horizon": w["horizon"],
            "baseline_score": round(base, 1), "score": round(score, 1), "delta": round(delta, 1),
        })
    except Exception:
        pass


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
        # approved by policy (no second approval required) — run the playbook now
        task = _run_playbook(session, org_id, actor, did, action, entity_id=entity_id, entity_name=entity_name,
                             scenario=scenario, horizon=horizon, rationale=rationale)
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
        task = _run_playbook(session, org_id, actor, did, p.get("action"), entity_id=p.get("entity_id"),
                             entity_name=p.get("entity_name"), scenario=p.get("scenario"),
                             horizon=p.get("horizon"), rationale=p.get("rationale"))
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
