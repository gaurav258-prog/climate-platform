"""One-time cleanup: give the demo supervisory body its own organisation id.

scripts/seed_auth_demo.py seeded "EU Climate Supervisor (demo)" under 55555555-…, the id scripts/seed_demo_supply.py
already owned for Terra Foods. The two seeds fought over the organisations row, Terra's people appeared inside the
regulator's team, and the regulator carried Terra's supply-chain data. Terra keeps 55555555-… (older, referenced by
every agriculture seed and test); the regulator moves to 88888888-… with ONLY its own rows:
people @supervisor.demo, its role templates, supervision scope/assignments/submissions, its settings and
entitlements, the shadow books it rebuilt, and the audit rows its people wrote.

Idempotent — a database where the split already happened is a no-op.

    .venv/bin/python scripts/fix_supervisor_org_split.py
"""
from __future__ import annotations

from sqlalchemy import text

from core.db.session import get_session
from services.governance.tenant_provisioning import role_templates_for

TERRA = "55555555-5555-4555-8555-555555555555"
SUPERVISOR = "88888888-8888-4888-8888-888888888888"
SUP_EMAIL = "%@supervisor.demo"


def main() -> None:
    with get_session() as s:
        already = s.execute(text("SELECT 1 FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": SUPERVISOR}).first()
        stray = s.execute(text("SELECT count(*) FROM users WHERE org_id = CAST(:o AS uuid) AND email LIKE :e"),
                          {"o": TERRA, "e": SUP_EMAIL}).scalar()
        if already and not stray:
            print("already split — nothing to do"); return

        # names are unique: hand the old row back to Terra before the regulator's row is created
        s.execute(text("""UPDATE organizations SET name = 'Terra Foods (demo)', type = 'manufacturer', country = 'ES'
                          WHERE org_id = CAST(:o AS uuid)"""), {"o": TERRA})
        s.execute(text("""
            INSERT INTO organizations (org_id, name, type, country, aum_eur, employees, created_at, updated_at)
            VALUES (CAST(:o AS uuid), 'EU Climate Supervisor (demo)', 'regulator', 'DE', NULL, 900, now(), now())
            ON CONFLICT (org_id) DO NOTHING"""), {"o": SUPERVISOR})

        # 1) roles: the regulator's templates move as they are; 'admin' exists for both tenants, so the regulator
        #    gets a fresh admin role with its own template and Terra keeps the original.
        templates = role_templates_for("regulator")
        moved_roles = [n for n in templates if n != "admin"]
        s.execute(text("UPDATE roles SET org_id = CAST(:n AS uuid) WHERE org_id = CAST(:o AS uuid) AND name = ANY(:names)"),
                  {"n": SUPERVISOR, "o": TERRA, "names": moved_roles})
        for name, perms in templates.items():
            rid = s.execute(text("SELECT role_id FROM roles WHERE org_id = CAST(:o AS uuid) AND name = :n"),
                            {"o": SUPERVISOR, "n": name}).scalar()
            if rid is None:
                rid = s.execute(text("""INSERT INTO roles (org_id, name, description, is_system)
                                        VALUES (CAST(:o AS uuid), :n, :d, true) RETURNING role_id"""),
                                {"o": SUPERVISOR, "n": name, "d": f"{name} role"}).scalar()
            for code in perms:
                s.execute(text("""INSERT INTO role_permissions (role_id, permission_id)
                                  SELECT :r, permission_id FROM permissions WHERE code = :c ON CONFLICT DO NOTHING"""),
                          {"r": rid, "c": code})

        # 2) people: move the regulator's users, re-point their 'admin' grant, drop stray tenant-template grants
        sup_users = s.execute(text("SELECT user_id FROM users WHERE org_id = CAST(:o AS uuid) AND email LIKE :e"),
                              {"o": TERRA, "e": SUP_EMAIL}).scalars().all()
        s.execute(text("UPDATE users SET org_id = CAST(:n AS uuid) WHERE org_id = CAST(:o AS uuid) AND email LIKE :e"),
                  {"n": SUPERVISOR, "o": TERRA, "e": SUP_EMAIL})
        new_admin = s.execute(text("SELECT role_id FROM roles WHERE org_id = CAST(:o AS uuid) AND name = 'admin'"),
                              {"o": SUPERVISOR}).scalar()
        old_admin = s.execute(text("SELECT role_id FROM roles WHERE org_id = CAST(:o AS uuid) AND name = 'admin'"),
                              {"o": TERRA}).scalar()
        for uid in sup_users:
            if s.execute(text("SELECT 1 FROM user_roles WHERE user_id = :u AND role_id = :r"), {"u": uid, "r": old_admin}).first():
                s.execute(text("DELETE FROM user_roles WHERE user_id = :u AND role_id = :r"), {"u": uid, "r": old_admin})
                s.execute(text("INSERT INTO user_roles (user_id, role_id) VALUES (:u, :r) ON CONFLICT DO NOTHING"),
                          {"u": uid, "r": new_admin})
            # grants on roles that stayed with Terra (its own admin/analyst/approver/viewer) are not the regulator's
            s.execute(text("""DELETE FROM user_roles WHERE user_id = :u AND role_id IN
                              (SELECT role_id FROM roles WHERE org_id = CAST(:o AS uuid))"""), {"u": uid, "o": TERRA})
        s.execute(text("UPDATE refresh_token SET org_id = CAST(:n AS uuid) WHERE user_id = ANY(CAST(:ids AS uuid[]))"),
                  {"n": SUPERVISOR, "ids": [str(u) for u in sup_users]})

        # 3) the regulator's own data
        for tbl in ("supervision_scope", "supervisor_submissions", "supervision_assignment"):
            s.execute(text(f"UPDATE {tbl} SET regulator_org_id = CAST(:n AS uuid) WHERE regulator_org_id = CAST(:o AS uuid)"),
                      {"n": SUPERVISOR, "o": TERRA})
        s.execute(text("UPDATE supervisor_settings SET org_id = CAST(:n AS uuid) WHERE org_id = CAST(:o AS uuid)"),
                  {"n": SUPERVISOR, "o": TERRA})
        s.execute(text("""UPDATE portfolio_entities SET org_id = CAST(:n AS uuid)
                          WHERE org_id = CAST(:o AS uuid) AND source = 'supervisor_shadow'"""), {"n": SUPERVISOR, "o": TERRA})
        s.execute(text("""UPDATE access_audit_log SET org_id = CAST(:n AS uuid)
                          WHERE org_id = CAST(:o AS uuid) AND actor_user_id = ANY(CAST(:ids AS uuid[]))"""),
                  {"n": SUPERVISOR, "o": TERRA, "ids": [str(u) for u in sup_users]})
        s.execute(text("DELETE FROM org_entitlements WHERE org_id = CAST(:o AS uuid) AND offering_id = 'supervision'"), {"o": TERRA})
        for off in ("supervision", "trust"):
            s.execute(text("""INSERT INTO org_entitlements (org_id, offering_id, enabled) VALUES (CAST(:o AS uuid), :f, true)
                              ON CONFLICT (org_id, offering_id) DO UPDATE SET enabled = true"""), {"o": SUPERVISOR, "f": off})
        s.commit()
        n = s.execute(text("SELECT count(*) FROM users WHERE org_id = CAST(:o AS uuid)"), {"o": SUPERVISOR}).scalar()
        m = s.execute(text("SELECT count(*) FROM portfolio_entities WHERE org_id = CAST(:o AS uuid)"), {"o": SUPERVISOR}).scalar()
        print(f"split done — regulator {SUPERVISOR}: {len(sup_users)} people moved ({n} now), {m} shadow rows; Terra keeps {TERRA}")


if __name__ == "__main__":
    main()
