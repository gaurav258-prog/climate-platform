"""Transmission — submission case & regulator-communication tracker (institution side).

A case per submission with a five-stage tracker (ready → submitted → query → answered → closed) and an
append-only message thread, so all correspondence about a filing lives in one auditable place. The actual
transmission channel to a regulator portal is external — this records and tracks it, it does not send.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

STAGES = ["ready", "submitted", "query", "answered", "closed"]


class CaseError(ValueError):
    pass


def list_cases(session: Session, org_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT c.case_id::text AS case_id, c.regulator, c.reference, c.stage, c.updated_at,
               c.filing_id::text AS filing_id, rf.framework, rf.period_label,
               (SELECT count(*) FROM reg_case_message m WHERE m.case_id = c.case_id) AS n_msgs
        FROM reg_submission_case c
        LEFT JOIN regulatory_filing rf ON rf.filing_id = c.filing_id
        WHERE c.org_id = :o ORDER BY c.updated_at DESC
    """), {"o": org_id}).mappings().all()
    return [{"case_id": r["case_id"], "regulator": r["regulator"], "reference": r["reference"],
             "stage": r["stage"], "filing_id": r["filing_id"], "framework": r["framework"],
             "period_label": r["period_label"], "n_messages": r["n_msgs"],
             "updated_at": r["updated_at"].isoformat()} for r in rows]


def get_case(session: Session, org_id: str, case_id: str) -> dict | None:
    c = session.execute(text("""
        SELECT c.case_id::text AS case_id, c.regulator, c.reference, c.stage, c.created_at, c.updated_at,
               c.filing_id::text AS filing_id, rf.framework, rf.period_label
        FROM reg_submission_case c LEFT JOIN regulatory_filing rf ON rf.filing_id = c.filing_id
        WHERE c.org_id = :o AND c.case_id = :c
    """), {"o": org_id, "c": case_id}).mappings().first()
    if not c:
        return None
    msgs = session.execute(text("""
        SELECT direction, author, body, attachment_ref, created_at
        FROM reg_case_message WHERE case_id = :c ORDER BY created_at
    """), {"c": case_id}).mappings().all()
    return {**{k: c[k] for k in ("case_id", "regulator", "reference", "stage", "filing_id", "framework", "period_label")},
            "created_at": c["created_at"].isoformat(), "updated_at": c["updated_at"].isoformat(),
            "messages": [{"direction": m["direction"], "author": m["author"], "body": m["body"],
                          "attachment_ref": m["attachment_ref"], "at": m["created_at"].isoformat()} for m in msgs]}


def case_for_filing(session: Session, org_id: str, filing_id: str) -> dict | None:
    """The most-recent transmission case linked to a filing (so the filing drawer can jump to it)."""
    r = session.execute(text("""
        SELECT c.case_id::text AS case_id, c.regulator, c.reference, c.stage,
               (SELECT count(*) FROM reg_case_message m WHERE m.case_id = c.case_id) AS n_msgs
        FROM reg_submission_case c
        WHERE c.org_id = :o AND c.filing_id = :f
        ORDER BY c.updated_at DESC LIMIT 1
    """), {"o": org_id, "f": filing_id}).mappings().first()
    if not r:
        return None
    return {"case_id": r["case_id"], "regulator": r["regulator"], "reference": r["reference"],
            "stage": r["stage"], "n_messages": r["n_msgs"]}


def open_case(session: Session, org_id: str, actor: str, *, regulator: str, filing_id: str | None = None,
              reference: str | None = None) -> dict:
    if not (regulator or "").strip():
        raise CaseError("a case needs a regulator")
    cid = session.execute(text("""
        INSERT INTO reg_submission_case (org_id, filing_id, regulator, reference, stage, created_by)
        VALUES (:o, :f, :r, :ref, 'ready', :u) RETURNING case_id
    """), {"o": org_id, "f": filing_id, "r": regulator.strip(), "ref": reference, "u": actor}).scalar()
    _msg(session, str(cid), "outbound", "system", f"Case opened for {regulator.strip()}.", actor)
    return get_case(session, org_id, str(cid))


def advance_stage(session: Session, org_id: str, case_id: str, actor: str, stage: str) -> dict:
    if stage not in STAGES:
        raise CaseError(f"unknown stage '{stage}'")
    cur = session.execute(text("SELECT stage FROM reg_submission_case WHERE org_id=:o AND case_id=:c"),
                          {"o": org_id, "c": case_id}).scalar()
    if cur is None:
        raise CaseError("case not found")
    session.execute(text("UPDATE reg_submission_case SET stage=:s WHERE org_id=:o AND case_id=:c"),
                    {"s": stage, "o": org_id, "c": case_id})
    _msg(session, case_id, "outbound", "system", f"Stage moved: {cur} → {stage}.", actor)
    return get_case(session, org_id, case_id)


def post_message(session: Session, org_id: str, case_id: str, actor: str, *, direction: str,
                 author: str, body: str, attachment_ref: str | None = None) -> dict:
    if direction not in ("outbound", "inbound"):
        raise CaseError("direction must be outbound or inbound")
    if not (body or "").strip():
        raise CaseError("message body is required")
    ok = session.execute(text("SELECT 1 FROM reg_submission_case WHERE org_id=:o AND case_id=:c"),
                        {"o": org_id, "c": case_id}).first()
    if not ok:
        raise CaseError("case not found")
    _msg(session, case_id, direction, author.strip() or "user", body.strip(), actor, attachment_ref)
    # a bump so the case rises in the list (touch trigger updates updated_at)
    session.execute(text("UPDATE reg_submission_case SET reference = reference WHERE case_id = :c"), {"c": case_id})
    return get_case(session, org_id, case_id)


def _msg(session: Session, case_id: str, direction: str, author: str, body: str,
         actor: str, attachment_ref: str | None = None) -> None:
    session.execute(text("""
        INSERT INTO reg_case_message (case_id, direction, author, body, attachment_ref, actor_user_id)
        VALUES (:c, :d, :a, :b, :ar, :u)
    """), {"c": case_id, "d": direction, "a": author, "b": body, "ar": attachment_ref, "u": actor})
