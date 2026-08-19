"""Regulatory work tasks — the Kanban backbone.

A thin, auditable task service: create, list (grouped for a board), move between columns, assign, and
spin a task from a validation exception or an obligation without duplicating. Every change is written to
regulatory_task_event, and assignment fires a notification through the existing notification service.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

COLUMNS = ["icebox", "todo", "blocked", "doing", "review", "done"]
_CRIT = ("low", "normal", "high", "critical")


class TaskError(ValueError):
    pass


def _event(session: Session, task_id: str, kind: str, actor: str | None,
           from_val: str | None = None, to_val: str | None = None, note: str | None = None) -> None:
    session.execute(text("""
        INSERT INTO regulatory_task_event (task_id, kind, from_val, to_val, note, actor_user_id)
        VALUES (:t, :k, :fv, :tv, :n, :a)
    """), {"t": task_id, "k": kind, "fv": from_val, "tv": to_val, "n": note, "a": actor})


def _row(r) -> dict:
    return {
        "task_id": str(r["task_id"]), "title": r["title"], "description": r["description"],
        "status": r["status"], "criticality": r["criticality"],
        "assignee_user_id": str(r["assignee_user_id"]) if r["assignee_user_id"] else None,
        "assignee": r.get("assignee_name"), "assignee_email": r.get("assignee_email"),
        "filing_id": str(r["filing_id"]) if r["filing_id"] else None,
        "source": r["source"], "source_ref": r["source_ref"],
        "due_date": r["due_date"].isoformat() if r["due_date"] else None,
        "depends_on": [str(x) for x in (r["depends_on"] or [])],
        "position": r["position"], "created_by": r.get("created_by_name"),
        "created_at": r["created_at"].isoformat(), "updated_at": r["updated_at"].isoformat(),
    }


def list_tasks(session: Session, org_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT t.*, a.full_name AS assignee_name, a.email AS assignee_email, c.full_name AS created_by_name
        FROM regulatory_task t
        LEFT JOIN users a ON a.user_id = t.assignee_user_id
        LEFT JOIN users c ON c.user_id = t.created_by
        WHERE t.org_id = :o AND t.status <> 'cancelled'
        ORDER BY t.status, t.position, t.created_at
    """), {"o": org_id}).mappings().all()
    return [_row(r) for r in rows]


def board(session: Session, org_id: str) -> dict:
    """Tasks grouped into Kanban columns + a small summary."""
    tasks = list_tasks(session, org_id)
    cols = {c: [t for t in tasks if t["status"] == c] for c in COLUMNS}
    overdue = sum(1 for t in tasks if t["due_date"] and t["status"] not in ("done",)
                  and t["due_date"] < _today(session))
    return {"columns": [{"key": c, "tasks": cols[c]} for c in COLUMNS],
            "summary": {"total": len(tasks), "overdue": overdue,
                        "unassigned": sum(1 for t in tasks if not t["assignee_user_id"])}}


def _today(session: Session) -> str:
    return session.execute(text("SELECT CURRENT_DATE")).scalar().isoformat()


def create_task(session: Session, org_id: str, actor: str, *, title: str, description: str | None = None,
                criticality: str = "normal", assignee_user_id: str | None = None, filing_id: str | None = None,
                due_date: str | None = None, source: str = "manual", source_ref: str | None = None,
                depends_on: list[str] | None = None) -> dict:
    if not (title or "").strip():
        raise TaskError("a task needs a title")
    if criticality not in _CRIT:
        raise TaskError(f"criticality must be one of {_CRIT}")
    # a linked filing must belong to THIS org — never attach to another tenant's filing UUID
    if filing_id:
        owned = session.execute(text(
            "SELECT 1 FROM regulatory_filing WHERE filing_id = CAST(:f AS uuid) AND org_id = :o"),
            {"f": filing_id, "o": org_id}).first()
        if not owned:
            raise TaskError("linked filing not found in this organisation")
    # de-dupe: a live task already exists for this source_ref → return it rather than piling up
    if source_ref:
        existing = session.execute(text("""
            SELECT task_id FROM regulatory_task
            WHERE org_id = :o AND source = :s AND source_ref = :r AND status NOT IN ('done','cancelled')
        """), {"o": org_id, "s": source, "r": source_ref}).scalar()
        if existing:
            return get_task(session, org_id, str(existing))
    tid = session.execute(text("""
        INSERT INTO regulatory_task (org_id, title, description, criticality, assignee_user_id, filing_id,
                                     source, source_ref, due_date, depends_on, created_by,
                                     position, status)
        VALUES (:o, :ti, :d, :c, :a, :f, :s, :r, :dd, :dep, :cb,
                COALESCE((SELECT MAX(position)+1 FROM regulatory_task WHERE org_id=:o AND status='todo'), 0), 'todo')
        RETURNING task_id
    """), {"o": org_id, "ti": title.strip(), "d": description, "c": criticality, "a": assignee_user_id,
           "f": filing_id, "s": source, "r": source_ref, "dd": due_date,
           "dep": depends_on or [], "cb": actor}).scalar()
    _event(session, str(tid), "created", actor, to_val="todo", note=title.strip())
    return get_task(session, org_id, str(tid))


def get_task(session: Session, org_id: str, task_id: str) -> dict | None:
    r = session.execute(text("""
        SELECT t.*, a.full_name AS assignee_name, a.email AS assignee_email, c.full_name AS created_by_name
        FROM regulatory_task t
        LEFT JOIN users a ON a.user_id = t.assignee_user_id
        LEFT JOIN users c ON c.user_id = t.created_by
        WHERE t.org_id = :o AND t.task_id = :t
    """), {"o": org_id, "t": task_id}).mappings().first()
    if not r:
        return None
    out = _row(r)
    evs = session.execute(text("""
        SELECT e.kind, e.from_val, e.to_val, e.note, e.created_at, u.full_name AS actor
        FROM regulatory_task_event e LEFT JOIN users u ON u.user_id = e.actor_user_id
        WHERE e.task_id = :t ORDER BY e.created_at
    """), {"t": task_id}).mappings().all()
    out["events"] = [{"kind": e["kind"], "from": e["from_val"], "to": e["to_val"], "note": e["note"],
                      "at": e["created_at"].isoformat(), "actor": e["actor"]} for e in evs]
    out["attachments"] = list_attachments(session, org_id, task_id)
    return out


def _load(session: Session, org_id: str, task_id: str) -> dict:
    r = session.execute(text(
        "SELECT status, title, assignee_user_id FROM regulatory_task WHERE org_id=:o AND task_id=:t"),
        {"o": org_id, "t": task_id}).mappings().first()
    if not r:
        raise TaskError("task not found")
    return dict(r)


# Stage-gate enforced at the source: a card can only ADVANCE into a gated stage once that stage's mandatory
# conditions are met. The objective conditions are verified here from the task's own state (can't be faked);
# the human attestations must be supplied with the move and are recorded on the activity log. Any move path —
# board arrow, drag-and-drop, the task-drawer dropdown, or a raw API call — passes through this check.
_STAGE_ORDER = {"icebox": 0, "todo": 1, "blocked": 2, "doing": 3, "review": 4, "done": 5, "cancelled": 6}
_GATED_STAGES = {"doing", "review", "done"}


def _gate_check(session: Session, org_id: str, task_id: str, cur: dict, target: str, attestations) -> None:
    """Raise TaskError if a forward move into `target` doesn't clear that stage's mandatory gate."""
    forward = _STAGE_ORDER.get(target, 0) > _STAGE_ORDER.get(cur["status"], 0)
    if not forward or target not in _GATED_STAGES:
        return  # only advancing INTO a gated stage is gated; backward / sideways moves are free
    # objective conditions — read from the task's own state
    if target == "doing":
        if not cur.get("assignee_user_id"):
            raise TaskError("Assign an owner before moving this task into Doing.")
        dep = session.execute(text("""
            SELECT count(*) FROM regulatory_task d
            JOIN regulatory_task t ON d.task_id = ANY(t.depends_on)
            WHERE t.task_id = :t AND t.org_id = :o AND d.status <> 'done'
        """), {"t": task_id, "o": org_id}).scalar()
        if dep:
            raise TaskError(f"{dep} dependency task(s) are still open — clear them before starting.")
    if target == "review":
        desc = session.execute(text("SELECT description FROM regulatory_task WHERE org_id=:o AND task_id=:t"),
                               {"o": org_id, "t": task_id}).scalar()
        if not (desc or "").strip():
            raise TaskError("Record what was done (add a description) before sending this task to Review.")
    # human attestations — a gated forward move must carry its confirmed checklist
    items = [a for a in (attestations or []) if str(a).strip()]
    if not items:
        raise TaskError(f"Confirm the mandatory checklist for “{target}” before moving this task there.")


def move_task(session: Session, org_id: str, task_id: str, actor: str, status: str,
              attestations: list[str] | None = None) -> dict:
    if status not in ("icebox", "todo", "blocked", "doing", "review", "done", "cancelled"):
        raise TaskError(f"unknown status '{status}'")
    cur = _load(session, org_id, task_id)
    if cur["status"] == status:
        return get_task(session, org_id, task_id)
    _gate_check(session, org_id, task_id, cur, status, attestations)
    session.execute(text("""
        UPDATE regulatory_task SET status = :s,
            position = COALESCE((SELECT MAX(position)+1 FROM regulatory_task WHERE org_id=:o AND status=:s), 0)
        WHERE org_id = :o AND task_id = :t
    """), {"s": status, "o": org_id, "t": task_id})
    note = None
    if status in _GATED_STAGES and _STAGE_ORDER.get(status, 0) > _STAGE_ORDER.get(cur["status"], 0):
        confirmed = [str(a).strip() for a in (attestations or []) if str(a).strip()]
        if confirmed:
            note = "gate confirmed · " + " · ".join(confirmed)
    _event(session, task_id, "moved", actor, from_val=cur["status"], to_val=status, note=note)
    return get_task(session, org_id, task_id)


def update_task(session: Session, org_id: str, task_id: str, actor: str, *, title: str | None = None,
                description: str | None = None, criticality: str | None = None,
                due_date: str | None = None, clear_due: bool = False) -> dict:
    """Edit a task's fields (title / description / criticality / due date). Only supplied fields change."""
    cur = _load(session, org_id, task_id)
    if criticality is not None and criticality not in _CRIT:
        raise TaskError(f"criticality must be one of {_CRIT}")
    if title is not None and not title.strip():
        raise TaskError("title can't be empty")
    session.execute(text("""
        UPDATE regulatory_task SET
            title = COALESCE(:t, title),
            description = CASE WHEN :dset THEN :d ELSE description END,
            criticality = COALESCE(:c, criticality),
            due_date = CASE WHEN :ddclear THEN NULL WHEN CAST(:dd AS date) IS NOT NULL THEN CAST(:dd AS date) ELSE due_date END
        WHERE org_id = :o AND task_id = :tid
    """), {"t": title.strip() if title else None, "dset": description is not None, "d": description,
           "c": criticality, "ddclear": clear_due, "dd": due_date, "o": org_id, "tid": task_id})
    _event(session, task_id, "edited", actor, from_val=cur["title"],
           to_val=(title.strip() if title else None), note="fields updated")
    return get_task(session, org_id, task_id)


def comment(session: Session, org_id: str, task_id: str, actor: str, body: str,
            mentions: list[str] | None = None) -> dict:
    """Append a comment to a task's activity log (append-only). Any @mentioned colleagues (passed as user_ids
    the picker resolved) are recorded as mentions so they get pinged — for a question, a clarification, or a
    delegation. Mentions are validated to this org and a user is never mentioned to themselves."""
    _load(session, org_id, task_id)   # org-scope check
    body = (body or "").strip()
    if not body:
        raise TaskError("comment can't be empty")
    _event(session, task_id, "commented", actor, note=body)
    targets = {m for m in (mentions or []) if m and m != actor}
    if targets:
        _notify_mentions(session, org_id, task_id, actor, body, targets)
    return get_task(session, org_id, task_id)


def _notify_mentions(session: Session, org_id: str, task_id: str, actor: str, body: str, targets: set[str]) -> None:
    """Record each mention and queue an email ping to the mentioned colleague (delivered best-effort)."""
    from core.config import settings
    from services.notifications import mailer
    who = session.execute(text("""
        SELECT u.full_name AS actor, t.title AS task_title FROM regulatory_task t
        LEFT JOIN users u ON u.user_id = CAST(:a AS uuid)
        WHERE t.task_id = :t AND t.org_id = :o
    """), {"a": actor, "t": task_id, "o": org_id}).mappings().first()
    actor_name = (who or {}).get("actor") or "A colleague"
    task_title = (who or {}).get("task_title") or "a task"
    link = f"{settings.APP_BASE_URL}/tasks?task={task_id}"
    for uid in targets:
        rec = session.execute(text("SELECT email, full_name FROM users WHERE user_id = CAST(:u AS uuid) AND org_id = :o"),
                              {"u": uid, "o": org_id}).mappings().first()
        if not rec:
            continue  # skip anything not a member of this org — never mention across tenants
        mid = session.execute(text("""
            INSERT INTO regulatory_task_mention (org_id, task_id, mentioned_user, by_user, snippet)
            VALUES (:o, :t, CAST(:u AS uuid), :a, :s) RETURNING mention_id
        """), {"o": org_id, "t": task_id, "u": uid, "a": actor, "s": body[:280]}).scalar()
        subject = f"{actor_name} mentioned you on “{task_title}”"
        text_body = (f"{actor_name} mentioned you on the task “{task_title}”:\n\n  {body}\n\n"
                     f"Open the task: {link}\n")
        html = (f'<p><strong>{_esc(actor_name)}</strong> mentioned you on the task '
                f'“{_esc(task_title)}”:</p><blockquote style="margin:8px 0;padding:8px 12px;'
                f'border-left:3px solid #5cc8ff;color:#334">{_esc(body)}</blockquote>'
                f'<p><a href="{_esc(link)}">Open the task →</a></p>')
        mailer.queue_email(session, org_id=org_id, to_email=rec["email"], subject=subject,
                           html=html, text_body=text_body, kind="task_mention",
                           ref_type="task_mention", ref_id=str(mid))
    # dispatch: fast transports send inline (same transaction, instant); SMTP is handed to the Celery worker so
    # its handshake never adds latency to the comment. The Celery beat sweep guarantees delivery either way.
    mailer.dispatch(session)


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ── attachments ──────────────────────────────────────────────────────────────────────────────────────────
_MAX_ATTACH_BYTES = 15 * 1024 * 1024  # 15 MB — inline BYTEA, ample for the docs a filing task needs


def add_attachment(session: Session, org_id: str, task_id: str, actor: str, *, filename: str,
                   content_type: str | None, data: bytes) -> dict:
    _load(session, org_id, task_id)   # org-scope check
    if not (filename or "").strip():
        raise TaskError("the file needs a name")
    if not data:
        raise TaskError("the file is empty")
    if len(data) > _MAX_ATTACH_BYTES:
        raise TaskError(f"file is too large (max {_MAX_ATTACH_BYTES // (1024 * 1024)} MB)")
    aid = session.execute(text("""
        INSERT INTO regulatory_task_attachment (org_id, task_id, filename, content_type, size_bytes, data, uploaded_by)
        VALUES (:o, :t, :f, :ct, :sz, :d, :u) RETURNING attachment_id
    """), {"o": org_id, "t": task_id, "f": filename.strip(), "ct": content_type,
           "sz": len(data), "d": data, "u": actor}).scalar()
    _event(session, task_id, "attached", actor, note=filename.strip())
    return {"attachment_id": str(aid), "filename": filename.strip(), "size_bytes": len(data)}


def list_attachments(session: Session, org_id: str, task_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT a.attachment_id, a.filename, a.content_type, a.size_bytes, a.uploaded_at, u.full_name AS by
        FROM regulatory_task_attachment a LEFT JOIN users u ON u.user_id = a.uploaded_by
        WHERE a.org_id = :o AND a.task_id = :t ORDER BY a.uploaded_at DESC
    """), {"o": org_id, "t": task_id}).mappings().all()
    return [{"attachment_id": str(r["attachment_id"]), "filename": r["filename"], "content_type": r["content_type"],
             "size_bytes": r["size_bytes"], "by": r["by"], "at": r["uploaded_at"].isoformat()} for r in rows]


def get_attachment(session: Session, org_id: str, task_id: str, attachment_id: str) -> dict | None:
    r = session.execute(text("""
        SELECT filename, content_type, data FROM regulatory_task_attachment
        WHERE org_id = :o AND task_id = :t AND attachment_id = :a
    """), {"o": org_id, "t": task_id, "a": attachment_id}).mappings().first()
    if not r:
        return None
    return {"filename": r["filename"], "content_type": r["content_type"] or "application/octet-stream",
            "data": bytes(r["data"])}


def delete_attachment(session: Session, org_id: str, task_id: str, attachment_id: str, actor: str) -> None:
    fn = session.execute(text("""
        DELETE FROM regulatory_task_attachment WHERE org_id = :o AND task_id = :t AND attachment_id = :a
        RETURNING filename
    """), {"o": org_id, "t": task_id, "a": attachment_id}).scalar()
    if fn:
        _event(session, task_id, "removed_attachment", actor, note=fn)


# ── @mention inbox ───────────────────────────────────────────────────────────────────────────────────────
def my_mentions(session: Session, org_id: str, user_id: str) -> list[dict]:
    """Unread @mentions of this user across the org's tasks — the board's mentions inbox."""
    rows = session.execute(text("""
        SELECT m.mention_id, m.task_id, t.title, m.snippet, m.created_at, u.full_name AS by
        FROM regulatory_task_mention m
        JOIN regulatory_task t ON t.task_id = m.task_id
        LEFT JOIN users u ON u.user_id = m.by_user
        WHERE m.org_id = :o AND m.mentioned_user = CAST(:u AS uuid) AND m.read_at IS NULL
        ORDER BY m.created_at DESC
    """), {"o": org_id, "u": user_id}).mappings().all()
    return [{"mention_id": str(r["mention_id"]), "task_id": str(r["task_id"]), "task_title": r["title"],
             "snippet": r["snippet"], "by": r["by"], "at": r["created_at"].isoformat()} for r in rows]


def mark_mentions_seen(session: Session, org_id: str, task_id: str, user_id: str) -> None:
    """Mark this user's unread mentions on a task as read — called when they open the task."""
    session.execute(text("""
        UPDATE regulatory_task_mention SET read_at = now()
        WHERE org_id = :o AND task_id = :t AND mentioned_user = CAST(:u AS uuid) AND read_at IS NULL
    """), {"o": org_id, "t": task_id, "u": user_id})


def assign_task(session: Session, org_id: str, task_id: str, actor: str, assignee_user_id: str | None) -> dict:
    cur = _load(session, org_id, task_id)
    if assignee_user_id:
        ok = session.execute(text("SELECT 1 FROM users WHERE user_id = CAST(:a AS uuid) AND org_id = :o"),
                             {"a": assignee_user_id, "o": org_id}).first()
        if not ok:
            raise TaskError("assignee must be a user in this organisation")
    session.execute(text("UPDATE regulatory_task SET assignee_user_id = CAST(:a AS uuid) WHERE org_id=:o AND task_id=:t"),
                    {"a": assignee_user_id, "o": org_id, "t": task_id})
    _event(session, task_id, "assigned", actor,
           from_val=str(cur["assignee_user_id"]) if cur["assignee_user_id"] else None, to_val=assignee_user_id)
    return get_task(session, org_id, task_id)
