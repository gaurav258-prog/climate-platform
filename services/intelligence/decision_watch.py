"""The decision watchlist — what an approved 'monitor' decision opens (when the organisation's playbook enables it),
re-checked over time against the signal that raised the decision:

  crossing   the exposure's projected score under the scenario and horizon it was decided on (the worst priceable
             hazard, heat_acute excluded — the number the crossings rank on); it escalates when the score has risen
             by WATCH_DETERIORATION points or more since the watch opened
  loss       the asset's tested yearly loss as a share of the value its curve applies to, today
             (services.loss.signals.asset_share); it escalates when that share has risen since the watch opened —
             the tested figure itself worsened, so no margin is applied

One open watch per exposure and signal. Each escalation alerts the watcher and fires the webhook, best-effort.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

WATCH_REVIEW_DAYS = 90               # default re-review cadence for a 'monitor' watch (overridable per playbook)
WATCH_DETERIORATION = 2.0            # score points a watched crossing must worsen by to escalate on re-check


class WatchError(ValueError):
    pass


def projected_score(session: Session, org_id: str, entity_id: str, scenario: str | None,
                    horizon: str | None) -> float | None:
    """The worst priceable-hazard physical-risk score for one exposure under (scenario, horizon) — the same
    number the crossings view ranks on (heat_acute excluded, matching the headline convention)."""
    if not scenario or not horizon:
        return None
    return session.execute(text("""
        SELECT MAX(v.physical_risk_score)
        FROM v_portfolio_entity_physical_risk v
        WHERE v.org_id = :o AND v.entity_id = CAST(:e AS uuid) AND v.headline_eligible
          AND v.scenario = :s AND v.time_horizon = :h
    """), {"o": org_id, "e": entity_id, "s": scenario, "h": horizon}).scalar()


def open_watch(session: Session, org_id: str, actor: str, decision_id, *, signal: str, entity_id: str,
               entity_name: str | None, scenario: str | None, horizon: str | None, review_days: int) -> None:
    """Put the exposure on the watchlist with a re-review date, measured the way its signal measures it."""
    from services.loss.signals import asset_share
    score = projected_score(session, org_id, entity_id, scenario, horizon) if signal == "crossing" else None
    share = asset_share(session, org_id, entity_id) if signal == "loss" else None
    session.execute(text("""
        INSERT INTO decision_watchlist (org_id, entity_id, entity_name, scenario, horizon, decision_id, signal,
                                        baseline_score, baseline_share, review_date, added_by)
        VALUES (:o, CAST(:e AS uuid), :n, :s, :h, CAST(:d AS uuid), :sig, :score, :share,
                (CURRENT_DATE + (:rd || ' days')::interval)::date, :u)
        ON CONFLICT (org_id, entity_id, signal) WHERE status = 'watching' DO NOTHING
    """), {"o": org_id, "e": entity_id, "n": entity_name, "s": scenario, "h": horizon, "d": decision_id,
           "sig": signal, "score": score, "share": share, "rd": review_days, "u": actor})


def _r1(v):
    return round(v, 1) if v is not None else None


def watchlist(session: Session, org_id: str) -> list[dict]:
    """Open watches for this org — what Risk is actively watching, with the re-review date, what it was watched
    under (a projected score, or a tested-loss share), and (once re-checked) whether it has worsened."""
    rows = session.execute(text("""
        SELECT w.watch_id::text AS watch_id, w.entity_name, w.scenario, w.horizon, w.signal, w.baseline_score,
               w.baseline_share, w.review_date, w.status, w.last_checked_at, w.last_score, w.last_delta, w.last_share,
               u.email AS by, w.added_at
        FROM decision_watchlist w LEFT JOIN users u ON u.user_id = w.added_by
        WHERE w.org_id = :o AND w.status IN ('watching','escalated')
        ORDER BY (w.status = 'escalated') DESC, w.signal,
                 COALESCE(w.last_delta, w.last_share - w.baseline_share, 0) DESC, w.review_date NULLS LAST, w.watch_id
    """), {"o": org_id}).mappings().all()
    return [{"watch_id": r["watch_id"], "entity_name": r["entity_name"], "scenario": r["scenario"],
             "horizon": r["horizon"], "signal": r["signal"], "status": r["status"],
             "baseline_score": _r1(r["baseline_score"]), "last_score": _r1(r["last_score"]),
             "last_delta": _r1(r["last_delta"]), "baseline_share": r["baseline_share"], "last_share": r["last_share"],
             "review_date": r["review_date"].isoformat() if r["review_date"] else None,
             "last_checked_at": r["last_checked_at"].isoformat() if r["last_checked_at"] else None,
             "by": r["by"], "at": r["added_at"].isoformat()} for r in rows]


def resolve_watch(session: Session, org_id: str, watch_id: str, actor: str, status: str = "cleared") -> None:
    if status not in ("cleared", "escalated"):
        raise WatchError("status must be 'cleared' or 'escalated'")
    session.execute(text("""
        UPDATE decision_watchlist SET status = :s, resolved_by = :u, resolved_at = now()
        WHERE org_id = :o AND watch_id = CAST(:w AS uuid) AND status IN ('watching','escalated')
    """), {"s": status, "u": actor, "o": org_id, "w": watch_id})


def recheck_watchlist(session: Session, org_id: str | None = None, *, due_only: bool = False) -> list[dict]:
    """Re-check every open watch against the signal it was opened under and record the result; a watch that has
    worsened is ESCALATED and alerted. Returns the escalations. `due_only` (the scheduled beat) limits to watches
    past their review date; the manual trigger re-checks all. Each alert is best-effort."""
    from services.loss.signals import asset_share, carried
    clause = "w.org_id = :o AND" if org_id else ""
    due = "AND (w.review_date IS NULL OR w.review_date <= CURRENT_DATE)" if due_only else ""
    rows = session.execute(text(f"""
        SELECT w.watch_id::text AS watch_id, w.org_id::text AS org_id, w.entity_id::text AS entity_id,
               w.entity_name, w.scenario, w.horizon, w.signal, w.baseline_score, w.baseline_share,
               w.added_by::text AS added_by
        FROM decision_watchlist w
        WHERE {clause} w.status = 'watching' {due}
    """), {"o": org_id} if org_id else {}).mappings().all()
    books: dict[str, dict] = {}                       # each organisation's carried loss figures, read once
    escalations = []
    for w in rows:
        if w["signal"] == "loss":
            c = books.setdefault(w["org_id"], carried(session, w["org_id"]))
            now, base = asset_share(session, w["org_id"], w["entity_id"], c), w["baseline_share"]
            worsened = now is not None and base is not None and now > base
            session.execute(text("""
                UPDATE decision_watchlist SET last_checked_at = now(), last_share = :v,
                       status = CASE WHEN :esc THEN 'escalated' ELSE status END
                WHERE watch_id = CAST(:w AS uuid)
            """), {"v": now, "esc": worsened, "w": w["watch_id"]})
        else:
            now, base = projected_score(session, w["org_id"], w["entity_id"], w["scenario"], w["horizon"]), w["baseline_score"]
            delta = (now - base) if (now is not None and base is not None) else None
            worsened = delta is not None and delta >= WATCH_DETERIORATION
            session.execute(text("""
                UPDATE decision_watchlist SET last_checked_at = now(), last_score = :sc, last_delta = :dl,
                       status = CASE WHEN :esc THEN 'escalated' ELSE status END
                WHERE watch_id = CAST(:w AS uuid)
            """), {"sc": now, "dl": delta, "esc": worsened, "w": w["watch_id"]})
        if not worsened:
            continue
        e = {"watch_id": w["watch_id"], "entity_name": w["entity_name"], "signal": w["signal"],
             "scenario": w["scenario"], "horizon": w["horizon"]}
        e.update({"baseline_share": base, "share": now} if w["signal"] == "loss"
                 else {"baseline_score": round(base, 1), "score": round(now, 1), "delta": round(now - base, 1)})
        escalations.append(e)
        _alert(session, w, e)
    return escalations


def _alert(session: Session, w: dict, e: dict) -> None:
    """A watched exposure has worsened further — notify the watcher and fire the webhook. Best-effort."""
    if e["signal"] == "loss":
        moved = f"tested yearly loss {100 * e['baseline_share']:.2f}% → {100 * e['share']:.2f}% of its value"
    else:
        moved = (f"projected risk score under {w['scenario']} · {w['horizon']} {e['baseline_score']:.0f} → "
                 f"{e['score']:.0f} (+{e['delta']:.0f})")
    try:
        from services.notifications import mailer
        email = session.execute(text("SELECT email FROM users WHERE user_id = CAST(:u AS uuid)"),
                                {"u": w["added_by"]}).scalar() if w.get("added_by") else None
        if email:
            oid = mailer.queue_email(
                session, org_id=w["org_id"], to_email=email,
                subject=f"Watchlist alert · {w['entity_name']} worsened further",
                html=f'<p>An exposure you are monitoring, <b>{w["entity_name"]}</b>, has worsened further: {moved}. '
                     f'It has been escalated on your watchlist.</p>',
                text_body=f"{w['entity_name']} worsened further: {moved}. Escalated on your watchlist.\n",
                kind="decision", ref_type="watch", ref_id=str(w["watch_id"]))
            if oid:
                mailer.dispatch(session)
    except Exception:
        pass
    try:
        from services.integrations.webhooks import emit_event
        emit_event(session, w["org_id"], "risk.watch.deteriorated", {**e, "entity_id": w["entity_id"]})
    except Exception:
        pass
