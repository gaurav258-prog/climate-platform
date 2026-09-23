"""Narrow every existing tenant's 'analyst' role to the new preparer permission set.

Companion to scripts/reconcile_role_perms.py, but the opposite operation: that script is strictly additive
(it only grants what a widened template adds, never revokes). This one REVOKES — the 2026-09-23 fix to
DEFAULT_ROLE_PERMS["analyst"] (services/governance/tenant_provisioning.py) narrows analyst from a second
tenant super-user down to a preparer role, and that only takes effect for NEW tenants unless existing
tenants' already-persisted role_permissions rows are explicitly revoked here.

Revokes exactly _ADMIN_AND_DECISION_PERMS (admin.users.manage, admin.roles.manage,
admin.approval_policy.manage, approvals.decide, board.attest) from every org's 'analyst' role — nothing else,
and never touches any other role. Idempotent: running it twice is a no-op the second time.

    .venv/bin/python -m scripts.narrow_analyst_role
"""
from __future__ import annotations

from sqlalchemy import text

from core.db.session import get_session
from services.governance.tenant_provisioning import _ADMIN_AND_DECISION_PERMS


def main() -> None:
    with get_session() as s:
        roles = s.execute(text("""
            SELECT r.role_id, r.org_id::text AS org_id, o.name AS org_name
            FROM roles r JOIN organizations o ON o.org_id = r.org_id
            WHERE r.name = 'analyst'
        """)).mappings().all()
        revoked = 0
        touched_orgs = 0
        for r in roles:
            res = s.execute(text("""
                DELETE FROM role_permissions
                WHERE role_id = :rid
                  AND permission_id IN (SELECT permission_id FROM permissions WHERE code = ANY(:codes))
            """), {"rid": r["role_id"], "codes": list(_ADMIN_AND_DECISION_PERMS)})
            if res.rowcount:
                revoked += res.rowcount
                touched_orgs += 1
        s.commit()
        print(f"checked {len(roles)} 'analyst' role(s) across all tenants — "
              f"revoked {revoked} grant(s) across {touched_orgs} org(s) "
              f"(permissions removed: {sorted(_ADMIN_AND_DECISION_PERMS)})")


if __name__ == "__main__":
    main()
