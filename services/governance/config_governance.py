"""Governed calc/reporting-config changes — always audited, optionally 4-eyes (audit T6).

Changing the reporting basis (scenario/horizon/materiality) or a calculation method (VaR/severity/
return-period) changes *what a filing shows*. Previously reporting-settings were audited but single-admin,
and calc-settings were neither audited nor gated. This routes both through the SAME approval machinery as
location edits: every change is written to the audit log, and if the org's approval matrix marks the
action as requiring approval, the change opens a 4-eyes request instead of applying directly.

Default is apply-directly (no policy row → `needs_approval` is False), so there is no surprise UX change;
an org enables 4-eyes for config by toggling `config.*` in the approval matrix.
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from api.services.rbac import write_audit
from services.governance.location_governance import needs_approval

_TITLES = {
    "config.reporting_settings": "Change the reporting basis",
    "config.calc_settings": "Change a calculation method",
}


def apply_config_change(session: Session, request_type: str, payload: dict,
                        actor_user_id: str, org_id: str) -> dict:
    """Apply a config change and audit it. The ONE apply path — used both for a direct change and
    when an approval is granted (dispatched from approvals.decide)."""
    if request_type == "config.calc_settings":
        from services.calc_settings import upsert_calc_settings
        result = upsert_calc_settings(session, org_id, payload, actor_user_id)
    elif request_type == "config.reporting_settings":
        from services.governance.reporting_settings import upsert_reporting_settings
        result = upsert_reporting_settings(session, org_id, payload, actor_user_id)
    else:
        raise ValueError(f"unknown config request_type '{request_type}'")
    write_audit(session, org_id=org_id, actor_user_id=actor_user_id, action=request_type,
                target_type="config", target_id=request_type.split(".", 1)[1], detail={"changes": payload})
    return result


def submit_or_apply_config(session: Session, *, org_id: str, actor_user_id: str,
                           request_type: str, updates: dict) -> dict:
    """Open a 4-eyes request if the matrix requires it for this action; else apply + audit directly."""
    changed = list(updates.keys())
    if needs_approval(session, org_id, request_type, changed):
        title = _TITLES.get(request_type, "Change configuration")
        rid = session.execute(text("""
            INSERT INTO approval_requests (org_id, request_type, title, payload, maker_user_id)
            VALUES (:o, :t, :ti, CAST(:p AS jsonb), :m) RETURNING request_id
        """), {"o": org_id, "t": request_type, "ti": title, "p": json.dumps(updates), "m": actor_user_id}).scalar()
        write_audit(session, org_id=org_id, actor_user_id=actor_user_id, action="approval.request",
                    target_type="approval", target_id=str(rid), detail={"request_type": request_type, "changes": updates})
        return {"status": "pending_approval", "request_id": str(rid),
                "message": "This change needs a second approver (4-eyes). It is queued in Approvals."}
    result = apply_config_change(session, request_type, updates, actor_user_id, org_id)
    return {"status": "applied", "result": result}
