"""An undertaking's CSRD reporting role for a financial year (csrd_reporting_role): who files the sustainability
statement, individually (Directive 2013/34/EU Art. 19a), for the group (Art. 29a, by the parent undertaking), or not at
all because a parent's consolidated report includes it (the exemption of Art. 19a(9) / 29a(8) — the exempt subsidiary
states the parent's name, registered office and report), or voluntarily. A role is stated by one person and applies
when a second approves (four eyes, append-only); the ESRS statement is scoped by it (services.governance.esrs_statement).
"""
from __future__ import annotations

import json
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

ROLES = ("individual", "consolidated", "exempt_subsidiary", "voluntary")


class RoleError(ValueError):
    pass


def live_role(session: Session, org_id: str, entity_id: str | None, period_end: date) -> dict | None:
    r = session.execute(text("""
        SELECT role, parent_name, parent_registered_office, parent_report_ref, basis, recorded_at
        FROM v_csrd_reporting_role_live WHERE org_id = CAST(:o AS uuid)
          AND reporting_entity_id IS NOT DISTINCT FROM CAST(:e AS uuid) AND period_end = CAST(:pe AS date)
    """), {"o": org_id, "e": entity_id, "pe": str(period_end)[:10]}).mappings().first()
    return {**dict(r), "recorded_at": r["recorded_at"].isoformat()} if r else None


def request_role(session: Session, org_id: str, user_id: str, *, entity_id: str | None, period_end: date, role: str,
                 parent_name: str | None = None, parent_registered_office: str | None = None,
                 parent_report_ref: str | None = None, basis: str | None = None) -> dict:
    if role not in ROLES:
        raise RoleError(f"role must be one of {ROLES}")
    if role == "exempt_subsidiary" and not all((parent_name, parent_registered_office, parent_report_ref)):
        raise RoleError("an exempt subsidiary states the parent's name, registered office and consolidated report "
                        "(Art. 19a(9) / 29a(8))")
    if entity_id and not session.execute(text("SELECT 1 FROM reporting_entities WHERE entity_id = CAST(:e AS uuid) "
                                              "AND org_id = CAST(:o AS uuid)"), {"e": entity_id, "o": org_id}).first():
        raise RoleError("that undertaking is not one of this organisation's entities")
    if role == "consolidated" and entity_id and not session.execute(text(
            "SELECT 1 FROM reporting_entities WHERE parent_entity_id = CAST(:e AS uuid)"), {"e": entity_id}).first():
        raise RoleError("a consolidated statement is filed by the parent of a group — this entity has no subsidiaries")
    payload = {"entity_id": entity_id, "period_end": period_end.isoformat(), "role": role, "parent_name": parent_name,
               "parent_registered_office": parent_registered_office, "parent_report_ref": parent_report_ref, "basis": basis}
    rid = session.execute(text("""
        INSERT INTO approval_requests (org_id, request_type, title, payload, maker_user_id)
        VALUES (CAST(:o AS uuid), 'csrd.role', :t, CAST(:p AS jsonb), CAST(:m AS uuid)) RETURNING request_id::text
    """), {"o": org_id, "t": f"CSRD reporting role for the year ending {period_end}: {role.replace('_', ' ')}",
           "p": json.dumps(payload), "m": user_id}).scalar()
    return {"status": "pending", "approval_request_id": rid}


def apply_decision(session: Session, org_id: str, request_id: str, payload: dict, decision: str, checker: str) -> dict:
    if decision != "approved":
        return {"applied": False, "decision": decision}
    maker = session.execute(text("SELECT maker_user_id::text FROM approval_requests WHERE request_id = CAST(:r AS uuid)"),
                            {"r": request_id}).scalar()
    session.execute(text("""
        INSERT INTO csrd_reporting_role (org_id, reporting_entity_id, period_end, role, parent_name, parent_registered_office,
                                         parent_report_ref, basis, requested_by, approved_by, approval_request_id)
        VALUES (CAST(:o AS uuid), CAST(:e AS uuid), CAST(:pe AS date), :r, :pn, :po, :pr, :b, CAST(:m AS uuid),
                CAST(:c AS uuid), CAST(:q AS uuid))
    """), {"o": org_id, "e": payload.get("entity_id"), "pe": payload["period_end"], "r": payload["role"],
           "pn": payload.get("parent_name"), "po": payload.get("parent_registered_office"),
           "pr": payload.get("parent_report_ref"), "b": payload.get("basis"), "m": maker, "c": checker, "q": request_id})
    return {"applied": True, "role": payload["role"]}
