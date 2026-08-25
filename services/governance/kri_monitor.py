"""Detection lag — persist WHEN a KRI entered breach, so we can measure how long it sat before it was acted on.

The KRI grade is computed live; this module turns that live grade into a durable BREACH EPISODE
(kri_breach_episode). `observe()` is idempotent and safe to call on every dashboard read or from a scheduler:
it opens an episode on the first out-of-appetite observation (onset), tracks the worst value while the breach
persists, and closes it when the KRI returns within appetite. `acknowledge()` stamps the moment a human first
raises a remediation task. `detection_lag()` then reports pure timestamp facts — time in breach, and time from
onset to first action — never an estimate.

Honest limit, stated: onset is the first time the breach was OBSERVED. Observed continuously (a scheduler
calling observe on an interval) that equals the true onset to within the interval; observed only on dashboard
reads it is an upper bound on how early we could have known. Either way it is a real recorded event, not a guess.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

_SEV_RANK = {"amber": 1, "red": 2}


def _org_type(session: Session, org_id: str) -> Optional[str]:
    return session.execute(text("SELECT type FROM organizations WHERE org_id = CAST(:o AS uuid)"),
                           {"o": org_id}).scalar()


def _frameworks(session: Session, org_id: str, framework: Optional[str]) -> list[str]:
    if framework:
        return [framework]
    from services.governance.kri import kri_frameworks
    return [f["framework"] for f in kri_frameworks(_org_type(session, org_id))]


def observe(session: Session, org_id: str, framework: Optional[str] = None, result: Optional[dict] = None) -> dict:
    """Reconcile breach episodes against a live KRI evaluation. Idempotent. Returns {opened, updated, cleared}.
    Pass a precomputed kri() `result` to avoid a second evaluation when the caller already has one."""
    from services.governance.kri import kri as _kri
    opened = updated = cleared = 0
    for fw in _frameworks(session, org_id, framework):
        data = result if (result and result.get("framework") == fw) else _kri(session, org_id, fw)
        if not data or not data.get("supported"):
            continue
        breached_now = {}
        for k in data.get("kpis", []):
            if k.get("breached") and isinstance(k.get("value"), (int, float)):
                thr = k.get("red") if k.get("status") == "red" else k.get("amber")
                breached_now[k["key"]] = {
                    "label": k.get("label"), "severity": k.get("status"), "value": float(k["value"]),
                    "threshold": float(thr) if isinstance(thr, (int, float)) else None,
                    "direction": k.get("direction") or "higher_worse",
                }
        open_eps = {r["kri_key"]: r for r in session.execute(text("""
            SELECT episode_id::text AS episode_id, kri_key, severity, peak_value, direction
            FROM kri_breach_episode
            WHERE org_id = CAST(:o AS uuid) AND framework = :f AND cleared_at IS NULL
        """), {"o": org_id, "f": fw}).mappings().all()}

        for key, b in breached_now.items():
            ep = open_eps.get(key)
            if not ep:
                # generate the id here — the model's uuid default is ORM-side and never fires on a raw INSERT
                session.execute(text("""
                    INSERT INTO kri_breach_episode
                        (episode_id, org_id, framework, kri_key, label, severity, direction, onset_value, peak_value, threshold)
                    VALUES (CAST(:eid AS uuid), CAST(:o AS uuid), :f, :k, :l, :sev, :dir, :v, :v, :thr)
                    ON CONFLICT DO NOTHING
                """), {"eid": str(uuid.uuid4()), "o": org_id, "f": fw, "k": key, "l": b["label"], "sev": b["severity"],
                       "dir": b["direction"], "v": b["value"], "thr": b["threshold"]})
                opened += 1
                try:   # a newly opened breach is a real, discrete moment → connect/push (Export & Connect · Tier 3)
                    from services.integrations.webhooks import emit_event
                    emit_event(session, org_id, "kri.breached", {
                        "framework": fw, "kri_key": key, "label": b["label"],
                        "severity": b["severity"], "value": b["value"], "threshold": b["threshold"]})
                except Exception:
                    pass
                # Close the loop: a newly-opened breach auto-raises a remediation task (used to need a human
                # click), and a RED breach auto-opens the notifiability clock so a statutory window can't
                # silently run out. Both de-dupe on source_ref → safe to re-run every sweep.
                _auto_remediation_task(session, org_id, fw, key, b)
                if b["severity"] == "red":
                    _auto_notification_candidate(session, org_id, fw, key, b)
            else:
                worst = b["severity"] if _SEV_RANK.get(b["severity"], 0) > _SEV_RANK.get(ep["severity"], 0) else ep["severity"]
                pv = float(ep["peak_value"]) if ep["peak_value"] is not None else b["value"]
                peak = max(pv, b["value"]) if b["direction"] == "higher_worse" else min(pv, b["value"])
                session.execute(text("""
                    UPDATE kri_breach_episode SET severity = :sev, peak_value = :pk, last_seen_at = now()
                    WHERE episode_id = CAST(:e AS uuid)
                """), {"sev": worst, "pk": peak, "e": ep["episode_id"]})
                updated += 1

        for key, ep in open_eps.items():
            if key not in breached_now:
                session.execute(text("UPDATE kri_breach_episode SET cleared_at = now() WHERE episode_id = CAST(:e AS uuid)"),
                                {"e": ep["episode_id"]})
                cleared += 1
    session.commit()
    return {"opened": opened, "updated": updated, "cleared": cleared}


def _auto_remediation_task(session: Session, org_id: str, framework: str, key: str, b: dict) -> None:
    """A newly-opened breach auto-raises a remediation task (de-duped on source_ref) — the breach→task link that
    used to require a human click. System-actored (created_by NULL); swallows errors so it can't sink the sweep."""
    try:
        from services.governance import tasks as T
        crit = "high" if b.get("severity") == "red" else "normal"
        title = f"KRI breach — {b.get('label')}"[:300]
        desc = (f"Indicator '{b.get('label')}' entered breach, auto-detected by the KRI sweep: value {b.get('value')} "
                f"vs threshold {b.get('threshold')} ({b.get('severity')}). Framework {framework}. Review and remediate.")
        T.create_task(session, org_id, None, title=title, description=desc, criticality=crit,
                      source="kri", source_ref=f"{framework}:{key}")
    except Exception:
        pass


def _auto_notification_candidate(session: Session, org_id: str, framework: str, key: str, b: dict) -> None:
    """A RED breach auto-OPENS the notifiability clock so the 'notify the regulator within N hours' window starts
    counting instead of depending on someone remembering. HONEST: raising only opens the clock and de-dupes on
    source_ref; whether it is genuinely notifiable stays a human decision — a person confirms the actual
    notification (record) or dismisses it. Titled a candidate so it is never mistaken for a filed notification."""
    try:
        from services.governance import notification_clock as NC
        NC.raise_event(session, org_id,
                       title=f"Potentially notifiable — KRI breach: {b.get('label')} (confirm or dismiss)",
                       source_type="kri_breach_auto", source_ref=f"{framework}:{key}",
                       category="kri_breach", severity=b.get("severity"))
    except Exception:
        pass


def sweep(session: Session) -> dict:
    """Evaluate EVERY tenant's KRIs and reconcile breach episodes — the interval sweep that makes breach
    onset independent of who happens to open the dashboard, and drives the kri.breached webhook on its own.
    Idempotent and cheap (one open episode per indicator); safe to run hourly. Returns rollup counts."""
    orgs = session.execute(text("SELECT org_id::text AS org FROM organizations WHERE type <> 'platform'")).mappings().all()
    roll = {"orgs": 0, "opened": 0, "updated": 0, "cleared": 0}
    for o in orgs:
        try:
            r = observe(session, o["org"], None)   # observe() fans across the org's KRI frameworks itself
        except Exception:
            continue
        if r["opened"] or r["updated"] or r["cleared"]:
            roll["orgs"] += 1
        for k in ("opened", "updated", "cleared"):
            roll[k] += r[k]
    return roll


def acknowledge(session: Session, org_id: str, framework: str, kri_key: str, user_id: Optional[str]) -> None:
    """First human action on an open breach → stamp acknowledged_at once (idempotent)."""
    session.execute(text("""
        UPDATE kri_breach_episode SET acknowledged_at = now(), acknowledged_by = CAST(:u AS uuid)
        WHERE org_id = CAST(:o AS uuid) AND framework = :f AND kri_key = :k
          AND cleared_at IS NULL AND acknowledged_at IS NULL
    """), {"o": org_id, "f": framework, "k": kri_key, "u": user_id})
    session.commit()


def detection_lag(session: Session, org_id: str, framework: Optional[str] = None) -> dict:
    """Per-episode facts + honest aggregates. response lag = acknowledged_at − onset_at."""
    params, fclause = {"o": org_id}, ""
    if framework:
        fclause, params["f"] = "AND framework = :f", framework
    rows = session.execute(text(f"""
        SELECT framework, kri_key, label, severity, onset_at, acknowledged_at, cleared_at,
               EXTRACT(EPOCH FROM (COALESCE(cleared_at, now()) - onset_at)) AS in_breach_s,
               EXTRACT(EPOCH FROM (acknowledged_at - onset_at))            AS response_s
        FROM kri_breach_episode
        WHERE org_id = CAST(:o AS uuid) {fclause}
        ORDER BY (cleared_at IS NULL) DESC, onset_at DESC
    """), params).mappings().all()

    eps, resp_days, open_unack = [], [], []
    for r in rows:
        open_ = r["cleared_at"] is None
        ack = r["acknowledged_at"] is not None
        in_days = round(float(r["in_breach_s"] or 0) / 86400, 2)
        resp = round(float(r["response_s"]) / 86400, 2) if r["response_s"] is not None else None
        eps.append({
            "kri_key": r["kri_key"], "label": r["label"], "framework": r["framework"], "severity": r["severity"],
            "onset_at": r["onset_at"].isoformat(), "open": open_, "acknowledged": ack,
            "acknowledged_at": r["acknowledged_at"].isoformat() if ack else None,
            "cleared_at": r["cleared_at"].isoformat() if not open_ else None,
            "days_in_breach": in_days, "response_lag_days": resp,
        })
        if resp is not None:
            resp_days.append(resp)
        if open_ and not ack:
            open_unack.append(in_days)
    resp_days.sort()
    return {
        "episodes": eps,
        "summary": {
            "n_episodes": len(eps),
            "n_open": sum(1 for e in eps if e["open"]),
            "n_unacknowledged": sum(1 for e in eps if e["open"] and not e["acknowledged"]),
            "median_response_lag_days": (resp_days[len(resp_days) // 2] if resp_days else None),
            "worst_open_unacknowledged_days": (max(open_unack) if open_unack else None),
        },
    }
