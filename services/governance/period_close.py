"""The year-end close of one undertaking and period, and the restatement of a closed period's values.

A sustainability statement covers the reporting period of the financial statements and prints the previous period
beside it (ESRS 1 §73, §83); a material error in a closed period is corrected by restating it (ESRS 1 §96, §98 as
amended by Delegated Regulation (EU) 2026/1563). So a period is closed like the financial books: requested by one
person, approved by another (reporting_period_close, append-only, four eyes by CHECK). After the close the database
refuses any period-keyed value without a restatement reason (provided_datapoint, site_period_values); a correction
is requested here with its reason and lands only when a second person approves it. A filing frozen before the
correction is never touched — it is flagged that a restatement may be needed (data_revisions).

  request_close / close_blockers   ask to close (refused while a value for the period awaits attestation)
  request_site_value_restatement   a closed period's site carrying amount or net revenue, corrected with its reason
  apply_decision                   the approvals router's handler for both
  closes                           the closed periods of the organisation
"""
from __future__ import annotations

import json
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

MEASURES = {"carrying_amount": False, "carrying_amount_adapted": False, "net_revenue": True}   # → a yearly flow (average rate)?


class PeriodError(ValueError):
    pass


def is_closed(session: Session, org_id: str, entity_id: str | None, period_end: date | str) -> bool:
    return bool(session.execute(text("SELECT period_closed(CAST(:o AS uuid), CAST(:e AS uuid), CAST(:pe AS date))"),
                                {"o": org_id, "e": entity_id, "pe": str(period_end)[:10]}).scalar())


def _entity(session: Session, org_id: str, entity_id: str | None) -> str | None:
    if entity_id and not session.execute(text("SELECT 1 FROM reporting_entities WHERE entity_id = CAST(:e AS uuid) "
                                              "AND org_id = CAST(:o AS uuid)"), {"e": entity_id, "o": org_id}).first():
        raise PeriodError("that undertaking is not one of this organisation's entities")
    return entity_id


def close_blockers(session: Session, org_id: str, entity_id: str | None, period_end: date) -> list[str]:
    """Why the period cannot close yet: a value for it still awaiting its second person, or already closed."""
    out = []
    if is_closed(session, org_id, entity_id, period_end):
        out.append("the period is already closed")
    pending = session.execute(text("""
        SELECT count(*) FROM provided_datapoint WHERE org_id = CAST(:o AS uuid) AND status = 'pending'
          AND reporting_period_end = CAST(:pe AS date) AND reporting_entity_id IS NOT DISTINCT FROM CAST(:e AS uuid)
    """), {"o": org_id, "pe": period_end, "e": entity_id}).scalar()
    if pending:
        out.append(f"{pending} provided value(s) for the period await attestation")
    waiting = session.execute(text("""
        SELECT count(*) FROM approval_requests WHERE org_id = CAST(:o AS uuid) AND status = 'pending'
          AND request_type IN ('period.close', 'period.restate') AND payload->>'period_end' = :pe
          AND payload->>'entity_id' IS NOT DISTINCT FROM :e
    """), {"o": org_id, "pe": period_end.isoformat(), "e": entity_id}).scalar()
    if waiting:
        out.append("a close or restatement of this period already awaits its second person")
    return out


def request_close(session: Session, org_id: str, user_id: str, *, entity_id: str | None, period_end: date,
                  note: str | None = None) -> dict:
    entity_id = _entity(session, org_id, entity_id)
    blockers = close_blockers(session, org_id, entity_id, period_end)
    if blockers:
        raise PeriodError("cannot close: " + "; ".join(blockers))
    payload = {"kind": "close", "entity_id": entity_id, "period_end": period_end.isoformat(), "note": note}
    rid = session.execute(text("""
        INSERT INTO approval_requests (org_id, request_type, title, payload, maker_user_id)
        VALUES (CAST(:o AS uuid), 'period.close', :t, CAST(:p AS jsonb), CAST(:m AS uuid)) RETURNING request_id::text
    """), {"o": org_id, "t": f"Close the reporting period ending {period_end.isoformat()}", "p": json.dumps(payload),
           "m": user_id}).scalar()
    return {"status": "pending", "approval_request_id": rid}


def request_site_value_restatement(session: Session, org_id: str, user_id: str, *, site_id: str, period_end: date,
                                   measure: str, amount: float, currency: str, reason: str) -> dict:
    """A closed period's year-end value, corrected: converted now by the same rules (closing rate for the carrying
    amount, the year's average for revenue) so the approver sees the figure that will be stored."""
    from services.intake.money import MoneyError, convert_amount, field_entry
    if measure not in MEASURES:
        raise PeriodError(f"measure must be one of {sorted(MEASURES)}")
    if not (reason or "").strip() or len(reason.strip()) < 10:
        raise PeriodError("say why the closed period is restated (at least 10 characters)")
    if amount is None or amount < 0:
        raise PeriodError("the amount must be zero or more")
    site = session.execute(text("SELECT entity_id::text AS entity_id FROM sc_company_sites WHERE site_id = CAST(:s AS uuid) "
                                "AND org_id = CAST(:o AS uuid)"), {"s": site_id, "o": org_id}).mappings().first()
    if not site:
        raise PeriodError("site not found")
    if not is_closed(session, org_id, site["entity_id"], period_end):
        raise PeriodError("the period is open — send the value as a year-end value, not a restatement")
    try:
        conv = convert_amount(session, amount, currency, period_end, flow=MEASURES[measure], label=measure, org_id=org_id)
    except MoneyError as e:
        raise PeriodError(str(e)) from e
    entry = field_entry(conv["native"], conv["currency"], period_end, conv["eur"], conv["rate"], origin="restatement")
    payload = {"kind": "site_value", "site_id": site_id, "entity_id": site["entity_id"], "period_end": period_end.isoformat(),
               "measure": measure, "amount": conv["native"], "currency": conv["currency"], "amount_eur": conv["eur"],
               "money_source": entry, "reason": reason.strip()}
    rid = session.execute(text("""
        INSERT INTO approval_requests (org_id, request_type, title, payload, maker_user_id)
        VALUES (CAST(:o AS uuid), 'period.restate', :t, CAST(:p AS jsonb), CAST(:m AS uuid)) RETURNING request_id::text
    """), {"o": org_id, "t": f"Restate a site's {measure.replace('_', ' ')} for the closed period ending {period_end}",
           "p": json.dumps(payload, default=str), "m": user_id}).scalar()
    return {"status": "pending", "approval_request_id": rid, "amount_eur": conv["eur"]}


def apply_decision(session: Session, org_id: str, request_id: str, payload: dict, decision: str, checker: str) -> dict:
    """The approvals router's handler (four eyes enforced there: checker ≠ maker)."""
    if decision != "approved":
        return {"applied": False, "decision": decision}
    maker = session.execute(text("SELECT maker_user_id::text FROM approval_requests WHERE request_id = CAST(:r AS uuid)"),
                            {"r": request_id}).scalar()
    if payload.get("kind") == "close":
        pe = date.fromisoformat(payload["period_end"])
        blockers = [b for b in close_blockers(session, org_id, payload.get("entity_id"), pe)
                    if not b.startswith("a close or restatement")]          # this request itself is the one waiting
        if blockers:
            raise PeriodError("cannot close: " + "; ".join(blockers))
        session.execute(text("""
            INSERT INTO reporting_period_close (org_id, reporting_entity_id, period_end, requested_by, approved_by,
                                                approval_request_id, note)
            VALUES (CAST(:o AS uuid), CAST(:e AS uuid), CAST(:pe AS date), CAST(:m AS uuid), CAST(:c AS uuid),
                    CAST(:r AS uuid), :n)
        """), {"o": org_id, "e": payload.get("entity_id"), "pe": pe, "m": maker, "c": checker, "r": request_id,
               "n": payload.get("note")})
        return {"applied": True, "closed": payload["period_end"]}
    if payload.get("kind") == "site_value":
        session.execute(text("""
            INSERT INTO site_period_values (org_id, site_id, reporting_entity_id, period_end, measure, amount, currency,
                                            amount_eur, money_source, source, restatement_reason, recorded_by)
            VALUES (CAST(:o AS uuid), CAST(:s AS uuid), CAST(:e AS uuid), CAST(:pe AS date), :m, :a, :c, :eur,
                    CAST(:ms AS jsonb), 'client', :why, CAST(:by AS uuid))
        """), {"o": org_id, "s": payload["site_id"], "e": payload.get("entity_id"), "pe": payload["period_end"],
               "m": payload["measure"], "a": payload["amount"], "c": payload["currency"], "eur": payload["amount_eur"],
               "ms": json.dumps(payload["money_source"], default=str), "why": payload["reason"], "by": maker})
        return {"applied": True, "restated": payload["measure"]}
    raise PeriodError(f"unknown period request '{payload.get('kind')}'")


def closes(session: Session, org_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT c.reporting_entity_id::text AS entity_id, e.name AS entity_name, c.period_end, c.closed_at, c.note,
               rq.full_name AS requested_by, ap.full_name AS approved_by
        FROM reporting_period_close c
        LEFT JOIN reporting_entities e ON e.entity_id = c.reporting_entity_id
        LEFT JOIN users rq ON rq.user_id = c.requested_by LEFT JOIN users ap ON ap.user_id = c.approved_by
        WHERE c.org_id = CAST(:o AS uuid) ORDER BY c.period_end DESC, e.name
    """), {"o": org_id}).mappings().all()
    return [{**dict(r), "period_end": r["period_end"].isoformat(), "closed_at": r["closed_at"].isoformat()} for r in rows]
