"""Calc/reporting-config changes are audited and 4-eyes-governable (audit T6). Requires PostgreSQL.

Default (no policy row) = apply directly + audit. Toggle the action on in the approval matrix = a change
opens a 4-eyes request instead of applying. Self-cleaning (approval_requests / approval_policy are not WORM).
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.calc_settings import get_calc_settings
from services.governance.config_governance import submit_or_apply_config

RT = "config.calc_settings"


def _ctx(s):
    org = str(s.execute(text("SELECT org_id FROM organizations WHERE name ILIKE '%Terra%' LIMIT 1")).scalar())
    usr = str(s.execute(text("SELECT user_id FROM users WHERE org_id=:o LIMIT 1"), {"o": org}).scalar())
    return org, usr


@pytest.mark.integration
def test_default_applies_directly_and_audits():
    with get_session() as s:
        org, usr = _ctx(s)
        cur = get_calc_settings(s, org)
        # submit the CURRENT value (a no-op change) so behaviour is unchanged
        out = submit_or_apply_config(s, org_id=org, actor_user_id=usr, request_type=RT,
                                     updates={"assetmgmt_var_method": cur["assetmgmt_var_method"]})
        assert out["status"] == "applied"
        # an audit row for the config change exists
        n = s.execute(text("SELECT count(*) FROM access_audit_log WHERE org_id=:o AND action=:a"),
                      {"o": org, "a": RT}).scalar()
        assert n >= 1, "config change was not audited"


@pytest.mark.integration
def test_matrix_toggle_routes_to_four_eyes():
    with get_session() as s:
        org, usr = _ctx(s)
        cur = get_calc_settings(s, org)
        # turn on 4-eyes for this action for this org
        s.execute(text("""
            INSERT INTO approval_policy (org_id, action_key, requires_approval, material_fields)
            VALUES (:o, :a, TRUE, '[]'::jsonb)
            ON CONFLICT (org_id, action_key) WHERE org_id IS NOT NULL
            DO UPDATE SET requires_approval = TRUE
        """), {"o": org, "a": RT})
        s.commit()
    try:
        with get_session() as s:
            org, usr = _ctx(s)
            out = submit_or_apply_config(s, org_id=org, actor_user_id=usr, request_type=RT,
                                         updates={"assetmgmt_var_method": cur["assetmgmt_var_method"]})
            assert out["status"] == "pending_approval" and out.get("request_id"), \
                "config change did not open a 4-eyes request when the matrix required it"
    finally:
        with get_session() as s:
            org, _ = _ctx(s)
            s.execute(text("DELETE FROM approval_requests WHERE org_id=:o AND request_type=:a AND status='pending'"),
                      {"o": org, "a": RT})
            s.execute(text("DELETE FROM approval_policy WHERE org_id=:o AND action_key=:a"), {"o": org, "a": RT})
            s.commit()
