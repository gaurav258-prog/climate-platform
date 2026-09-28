"""The three views of an organisation's book — which values of each asset fact the engine reads (intake phase 5).

  joint     the book as resolved: the client's values, ours only where a person chose ours (the default)
  client    the client's own statements only — where ours was adopted, the client's value is put back
  tellumen  our value wherever we derive one independently (observations.DERIVERS), the client's everywhere else

The views can differ only in facts Tellumen derives; every other fact is the client's in all three. A view is computed,
never stored: in_view() records the book (observations.sync), then inside a SAVEPOINT rewrites just the facts that
differ, runs the engine exactly as for the live book — so every read path sees the same view — and rolls back. A commit
attempted inside is refused, so a view can never leak into the book.
"""
from __future__ import annotations

from collections import Counter
from typing import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.intake import observations as O

VIEWS = ("joint", "client", "tellumen")
LABEL = {"joint": "Joint — your values; ours only where you chose ours",
         "client": "Your values only",
         "tellumen": "Tellumen's value wherever we derive one; yours everywhere else"}


class ViewError(ValueError):
    pass


def substitutions(session: Session, org_id: str, view: str) -> list[dict]:
    """Every fact whose value in `view` differs from the live book: {table, id_column, asset_id, field, live, value}."""
    if view == "joint":
        return []
    out, seen_assets = [], set()
    for book in O.books():
        fields = [d.field for d in O.DERIVERS if d.field in book.fields]
        if not fields:
            continue
        rows = [r for r in book.load(session, org_id) if (book.table, r["entity_id"]) not in seen_assets]
        if not rows:
            continue
        seen_assets |= {(book.table, r["entity_id"]) for r in rows}
        stated = O.latest(session, org_id, book.table, [r["entity_id"] for r in rows])
        for r in rows:
            for f in fields:
                live = O.norm(r.get(f))
                c, t = stated.get((r["entity_id"], f, "client")), stated.get((r["entity_id"], f, "tellumen"))
                if view == "client":
                    value = O.norm(c["value"]) if c else live
                else:
                    value = O.norm(t["value"]) if t and t["value"] is not None else live
                if not O.same(value, live):
                    out.append({"table": book.table, "id_column": book.id_column, "asset_id": r["entity_id"],
                                "field": f, "live": live, "value": value})
    return out


def _refuse_commit():
    raise ViewError("a commit was attempted while computing a view — refused, so the view cannot reach the book")


def in_view(session: Session, org_id: str, view: str, fn: Callable[[], object]) -> tuple[object, dict]:
    """(fn's result computed on `view`, what the view changed)."""
    if view not in VIEWS:
        raise ViewError(f"unknown view '{view}' — one of {', '.join(VIEWS)}")
    O.sync(session, org_id)                                   # the book as it stands, recorded first
    subs = substitutions(session, org_id, view)
    record = {"view": view, "label": LABEL[view], "facts_changed": len(subs),
              "by_field": dict(Counter(s["field"] for s in subs)),
              "note": ("the views differ only in facts Tellumen derives independently: "
                       + ", ".join(sorted({d.field for d in O.DERIVERS})))}
    if not subs:
        return fn(), record
    sp = session.begin_nested()
    had = session.__dict__.get("commit")                     # a caller's own override (e.g. a test's) is restored after
    session.commit = _refuse_commit                          # instance attribute: this session only
    try:
        for s in subs:                                        # table / column names come from the registry, never input
            session.execute(text(f"UPDATE {s['table']} SET {s['field']} = :v WHERE {s['id_column']} = CAST(:a AS uuid) "
                                 "AND org_id = CAST(:o AS uuid)"), {"v": s["value"], "a": s["asset_id"], "o": org_id})
        result = fn()
    finally:
        if had is not None:
            session.commit = had
        else:
            session.__dict__.pop("commit", None)
        sp.rollback()
    return result, record


def preview(session: Session, org_id: str) -> dict:
    """How far each view is from the book, per fact — shown before a filing is prepared."""
    O.sync(session, org_id)
    out = {}
    for v in VIEWS:
        subs = substitutions(session, org_id, v)
        out[v] = {"label": LABEL[v], "facts_changed": len(subs), "by_field": dict(Counter(s["field"] for s in subs))}
    return out
