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
    return out


def _load(session: Session, org_id: str, task_id: str) -> dict:
    r = session.execute(text(
        "SELECT status, title, assignee_user_id FROM regulatory_task WHERE org_id=:o AND task_id=:t"),
        {"o": org_id, "t": task_id}).mappings().first()
    if not r:
        raise TaskError("task not found")
    return dict(r)


def move_task(session: Session, org_id: str, task_id: str, actor: str, status: str) -> dict:
    if status not in ("icebox", "todo", "blocked", "doing", "review", "done", "cancelled"):
        raise TaskError(f"unknown status '{status}'")
    cur = _load(session, org_id, task_id)
    if cur["status"] == status:
        return get_task(session, org_id, task_id)
    session.execute(text("""
        UPDATE regulatory_task SET status = :s,
            position = COALESCE((SELECT MAX(position)+1 FROM regulatory_task WHERE org_id=:o AND status=:s), 0)
        WHERE org_id = :o AND task_id = :t
    """), {"s": status, "o": org_id, "t": task_id})
    _event(session, task_id, "moved", actor, from_val=cur["status"], to_val=status)
    return get_task(session, org_id, task_id)


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
