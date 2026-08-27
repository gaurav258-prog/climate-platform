"""Reconcile existing tenants to the current DEFAULT_ROLE_PERMS matrix.

New-tenant provisioning already seeds roles from DEFAULT_ROLE_PERMS. This backfills tenants created BEFORE a
matrix change: it ensures the catalog holds every code the matrix references, then grants each system role
(matched by name) any permission it is missing. Additive and idempotent — it never revokes, so hand-edited
role customizations are preserved. Run after adding permissions or widening a role (e.g. analyst → super-user).

    .venv/bin/python -m scripts.reconcile_role_perms
"""
from __future__ import annotations

from sqlalchemy import text

from core.db.session import get_session
from services.governance.tenant_provisioning import DEFAULT_ROLE_PERMS

# Catalog descriptions for codes the matrix may reference that aren't guaranteed present yet.
CATALOG = {
    "oversight.view": "See the Supervisory view — how a regulator will read your data",
    "ops.oversee": "Operate the control surfaces — Control Tower exceptions and the compliance calendar",
    "decisions.view": "See and work the Decisions surface (reprice / engage / act)",
}


def main() -> None:
    with get_session() as s:
        # 1) ensure catalog codes exist
        for code, desc in CATALOG.items():
            s.execute(text("INSERT INTO permissions (code, description) VALUES (:c, :d) "
                           "ON CONFLICT (code) DO NOTHING"), {"c": code, "d": desc})

        # 2) grant each system role its full matrix (additive)
        granted = 0
        for role_name, perms in DEFAULT_ROLE_PERMS.items():
            role_ids = [r[0] for r in s.execute(
                text("SELECT role_id FROM roles WHERE name = :n"), {"n": role_name}).all()]
            for rid in role_ids:
                for code in perms:
                    res = s.execute(text("""
                        INSERT INTO role_permissions (role_id, permission_id)
                        SELECT :r, permission_id FROM permissions WHERE code = :c
                        ON CONFLICT DO NOTHING
                    """), {"r": rid, "c": code})
                    granted += res.rowcount or 0
        s.commit()
        n_roles = s.execute(text("SELECT count(*) FROM roles WHERE name = ANY(:names)"),
                            {"names": list(DEFAULT_ROLE_PERMS.keys())}).scalar()
        print(f"reconciled {n_roles} system role(s) across all tenants — {granted} new grant(s) added")


if __name__ == "__main__":
    main()
