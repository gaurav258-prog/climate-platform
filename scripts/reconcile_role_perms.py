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
from services.governance.tenant_provisioning import role_templates_for

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

        # 2) per tenant, by ORG TYPE: create any template role that is missing, then grant its matrix (additive).
        #    Supervisory bodies take their templates from the supervision-profile registry; others DEFAULT_ROLE_PERMS.
        granted = created = 0
        orgs = s.execute(text("SELECT org_id::text AS org_id, type FROM organizations WHERE type <> 'platform'")).mappings().all()
        for o in orgs:
            for role_name, perms in role_templates_for(o["type"]).items():
                rid = s.execute(text("SELECT role_id FROM roles WHERE org_id = CAST(:o AS uuid) AND name = :n"),
                                {"o": o["org_id"], "n": role_name}).scalar()
                if rid is None:
                    rid = s.execute(text("""INSERT INTO roles (org_id, name, description, is_system)
                                            VALUES (CAST(:o AS uuid), :n, :d, true) RETURNING role_id"""),
                                    {"o": o["org_id"], "n": role_name, "d": f"{role_name} role"}).scalar()
                    created += 1
                for code in perms:
                    res = s.execute(text("""
                        INSERT INTO role_permissions (role_id, permission_id)
                        SELECT :r, permission_id FROM permissions WHERE code = :c
                        ON CONFLICT DO NOTHING
                    """), {"r": rid, "c": code})
                    granted += res.rowcount or 0
        s.commit()
        print(f"reconciled {len(orgs)} tenant(s) — {created} role(s) created, {granted} new grant(s) added")


if __name__ == "__main__":
    main()
