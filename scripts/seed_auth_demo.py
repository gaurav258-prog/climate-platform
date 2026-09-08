"""
Seed demo auth: organizations, per-tenant entitlements, RBAC roles + permission
matrix, and demo users so the login flow can be exercised end-to-end.

Idempotent (safe to re-run). Passwords are bcrypt-hashed via api.security.

Demo credentials
----------------
  admin@meridian.demo    / Demo!admin1     (Meridian Bank · admin)
  analyst@meridian.demo  / Demo!analyst1   (Meridian Bank · analyst)
  approver@meridian.demo / Demo!approve1   (Meridian Bank · approver)
  admin@iberia.demo      / Demo!admin1     (Iberia Mutual · admin)
  analyst@iberia.demo    / Demo!analyst1   (Iberia Mutual · analyst)
  admin@stellar.demo     / Demo!admin1     (Stellar Logistics REIT · admin)
  analyst@stellar.demo   / Demo!analyst1   (Stellar Logistics REIT · analyst)
  admin@nordkap.demo     / Demo!admin1     (Nordkap Asset Management · admin)
  analyst@nordkap.demo   / Demo!analyst1   (Nordkap Asset Management · analyst)

Run:  .venv/bin/python scripts/seed_auth_demo.py
"""
from sqlalchemy import text

from api.security import hash_password
from core.db.session import get_session
from services.governance.tenant_provisioning import role_templates_for

MERIDIAN = "11111111-1111-4111-8111-111111111111"
IBERIA   = "22222222-2222-4222-8222-222222222222"
STELLAR  = "33333333-3333-4333-8333-333333333333"
NORDKAP  = "44444444-4444-4444-8444-444444444444"
SUPERVISOR = "88888888-8888-4888-8888-888888888888"   # banking supervisor demo tenant (55555555-… is Terra Foods)
INS_SUP    = "88888888-8888-4888-8888-888888888802"   # insurance supervisor
MKT_SUP    = "88888888-8888-4888-8888-888888888803"   # securities / markets supervisor
AGRI_SUP   = "88888888-8888-4888-8888-888888888804"   # agri-food authority
ORANJE     = "66666666-6666-4666-8666-666666666666"
# one supervisory body per sector, each with the profile that covers exactly that sector (scope respects the profile)
SUPERVISORS = {
    SUPERVISOR: ("banking_supervisor",   "supervisor",           [(MERIDIAN, "EU/SSM")]),
    INS_SUP:    ("insurance_supervisor", "insurance-supervisor", [(IBERIA, "EU/EIOPA")]),
    MKT_SUP:    ("markets_supervisor",   "markets-supervisor",   [(STELLAR, "EU/ESMA"), (NORDKAP, "EU/ESMA")]),
    AGRI_SUP:   ("agrifood_authority",   "agrifood-authority",   [(ORANJE, "EU/CSRD")]),
}

ORGS = [
    # org_id, name, type, country, aum_eur, employees
    (MERIDIAN, "Meridian Bank (demo)", "bank",     "ES", 48_000_000_000, 4200),
    (IBERIA,   "Iberia Mutual (demo)", "insurer",  "ES", 12_000_000_000, 1800),
    (STELLAR,  "Stellar Logistics REIT (demo)", "reit", "NL", 3_600_000_000, 210),
    (NORDKAP,  "Nordkap Asset Management (demo)", "asset_manager", "SE", 22_000_000_000, 340),
    (SUPERVISOR, "EU Banking Supervisor (demo)", "regulator", "DE", None, 900),
    (INS_SUP,    "EU Insurance Supervisor (demo)", "regulator", "DE", None, 400),
    (MKT_SUP,    "EU Markets Supervisor (demo)", "regulator", "FR", None, 600),
    (AGRI_SUP,   "EU Agri-food Authority (demo)", "regulator", "IT", None, 300),
]

ENTITLEMENTS = {
    MERIDIAN: ["physical-risk", "reporting", "trust"],
    IBERIA:   ["underwriting", "parametric", "trust"],
    STELLAR:  ["portfolio-risk", "trust"],
    NORDKAP:  ["portfolio-var", "trust", "securities"],
    SUPERVISOR: ["supervision", "trust"], INS_SUP: ["supervision", "trust"], MKT_SUP: ["supervision", "trust"], AGRI_SUP: ["supervision", "trust"],
}

# Supervisory bodies: roles come from the supervision-profile registry (configuration), and the demo users carry
# the supervisory roles a real authority would give them — admin as the all-round demo persona.
EXTRA_USER_ROLES = {
    "admin@supervisor.demo":    ["supervisor", "risk_analyst", "data_steward", "inspector", "head"],
    "admin@insurance-supervisor.demo": ["supervisor", "risk_analyst", "data_steward", "inspector", "head"],
    "admin@markets-supervisor.demo":   ["supervisor", "risk_analyst", "data_steward", "inspector", "head"],
    "admin@agrifood-authority.demo":   ["supervisor", "risk_analyst", "data_steward", "inspector", "head"],
    "analyst@supervisor.demo":  ["risk_analyst"],
    "approver@supervisor.demo": ["supervisor"],   # line supervisor: sees only the entities assigned to them
}

# role name -> permission codes
ROLE_PERMS = {
    "admin": [
        "modules.view", "reports.view", "reports.publish", "pricing.view", "pricing.approve",
        "admin.users.manage", "admin.roles.manage", "admin.audit.view",
        "approvals.create", "approvals.view", "approvals.decide", "portal.use",
    ],
    "analyst":  ["modules.view", "reports.view", "pricing.view", "approvals.create", "portal.use"],
    "approver": ["modules.view", "reports.view", "pricing.view", "reports.publish",
                 "pricing.approve", "approvals.view", "approvals.decide", "portal.use"],
    "viewer":   ["modules.view", "reports.view", "pricing.view", "portal.use"],
}

# Permissions granted to a role by a LATER migration, not by this script's own
# ROLE_PERMS above (e.g. e2f3a4b5c6d7_bank_disclosure_submissions.py grants
# 'submissions.release' to 'approver'). Step 3 below resets each role's
# permissions to exactly ROLE_PERMS every run -- without this, that reset
# silently wipes out any such migration-granted extra, and re-running this
# script (e.g. to fix an unrelated org) would quietly break the maker/checker
# submission-release flow. Re-applied after the reset, every run.
EXTRA_ROLE_PERMS = {
    "approver": ["submissions.release"],
}

# email, full_name, password, org_id, role
USERS = [
    ("admin@meridian.demo",    "Mara Admin (Meridian)",    "Demo!admin1",   MERIDIAN, "admin"),
    ("analyst@meridian.demo",  "Ana Analyst (Meridian)",   "Demo!analyst1", MERIDIAN, "analyst"),
    ("approver@meridian.demo", "Pieter Approver (Meridian)", "Demo!approve1", MERIDIAN, "approver"),
    ("admin@iberia.demo",      "Iria Admin (Iberia)",      "Demo!admin1",   IBERIA,   "admin"),
    ("analyst@iberia.demo",    "Alba Analyst (Iberia)",    "Demo!analyst1", IBERIA,   "analyst"),
    ("approver@iberia.demo",   "Bruno Approver (Iberia)",  "Demo!approve1", IBERIA,   "approver"),
    ("admin@stellar.demo",     "Sven Admin (Stellar)",     "Demo!admin1",   STELLAR,  "admin"),
    ("analyst@stellar.demo",   "Sanne Analyst (Stellar)",  "Demo!analyst1", STELLAR,  "analyst"),
    ("approver@stellar.demo",  "Femke Approver (Stellar)", "Demo!approve1", STELLAR,  "approver"),
    ("admin@nordkap.demo",     "Nils Admin (Nordkap)",     "Demo!admin1",   NORDKAP,  "admin"),
    ("analyst@nordkap.demo",   "Nora Analyst (Nordkap)",   "Demo!analyst1", NORDKAP,  "analyst"),
    ("approver@nordkap.demo",  "Erik Approver (Nordkap)",  "Demo!approve1", NORDKAP,  "approver"),
    # supervisory body: base roles are the supervision-profile templates, not the tenant admin/analyst/approver trio
    ("admin@supervisor.demo",   "Sofia Supervisor (EU Climate Supervisor)", "Demo!admin1",   SUPERVISOR, "admin"),
    ("analyst@supervisor.demo", "Lars Examiner (EU Climate Supervisor)",    "Demo!analyst1", SUPERVISOR, "risk_analyst"),
    ("approver@supervisor.demo", "Mina Case Lead (EU Climate Supervisor)",  "Demo!approve1", SUPERVISOR, "supervisor"),
    ("admin@insurance-supervisor.demo",    "Ines Supervisor (EU Insurance Supervisor)", "Demo!admin1",   INS_SUP, "admin"),
    ("analyst@insurance-supervisor.demo",  "Ivo Examiner (EU Insurance Supervisor)",    "Demo!analyst1", INS_SUP, "risk_analyst"),
    ("approver@insurance-supervisor.demo", "Ida Case Lead (EU Insurance Supervisor)",   "Demo!approve1", INS_SUP, "supervisor"),
    ("admin@markets-supervisor.demo",      "Marc Supervisor (EU Markets Supervisor)",   "Demo!admin1",   MKT_SUP, "admin"),
    ("analyst@markets-supervisor.demo",    "Maja Examiner (EU Markets Supervisor)",     "Demo!analyst1", MKT_SUP, "risk_analyst"),
    ("approver@markets-supervisor.demo",   "Milo Case Lead (EU Markets Supervisor)",    "Demo!approve1", MKT_SUP, "supervisor"),
    ("admin@agrifood-authority.demo",      "Anna Supervisor (EU Agri-food Authority)",  "Demo!admin1",   AGRI_SUP, "admin"),
    ("analyst@agrifood-authority.demo",    "Aldo Examiner (EU Agri-food Authority)",    "Demo!analyst1", AGRI_SUP, "risk_analyst"),
    ("approver@agrifood-authority.demo",   "Alba Case Lead (EU Agri-food Authority)",   "Demo!approve1", AGRI_SUP, "supervisor"),
]


def main():
    with get_session() as s:
        # 1) organizations
        for org_id, name, typ, country, aum, emp in ORGS:
            s.execute(text("""
                INSERT INTO organizations (org_id, name, type, country, aum_eur, employees, created_at, updated_at)
                VALUES (:o, :n, :t, :c, :a, :e, now(), now())
                ON CONFLICT (org_id) DO UPDATE SET name = EXCLUDED.name, type = EXCLUDED.type
            """), {"o": org_id, "n": name, "t": typ, "c": country, "a": aum, "e": emp})

        # 2) entitlements
        for org_id, offerings in ENTITLEMENTS.items():
            for off in offerings:
                s.execute(text("""
                    INSERT INTO org_entitlements (org_id, offering_id, enabled)
                    VALUES (:o, :off, true)
                    ON CONFLICT (org_id, offering_id) DO UPDATE SET enabled = true
                """), {"o": org_id, "off": off})

        # 3) roles + permission matrix (per org)
        for org_id, *_ in ORGS:
            org_type = next(o[2] for o in ORGS if o[0] == org_id)
            templates = role_templates_for(org_type) if org_type == 'regulator' else ROLE_PERMS
            for role_name, perms in templates.items():
                s.execute(text("""
                    INSERT INTO roles (org_id, name, description, is_system)
                    VALUES (:o, :n, :d, true)
                    ON CONFLICT (org_id, name) DO NOTHING
                """), {"o": org_id, "n": role_name, "d": f"{role_name} role"})
                role_id = s.execute(text(
                    "SELECT role_id FROM roles WHERE org_id = :o AND name = :n"
                ), {"o": org_id, "n": role_name}).scalar()
                # deterministic matrix: clear then set
                s.execute(text("DELETE FROM role_permissions WHERE role_id = :r"), {"r": role_id})
                for code in perms + EXTRA_ROLE_PERMS.get(role_name, []):
                    s.execute(text("""
                        INSERT INTO role_permissions (role_id, permission_id)
                        SELECT :r, permission_id FROM permissions WHERE code = :c
                        ON CONFLICT DO NOTHING
                    """), {"r": role_id, "c": code})

        # 4) users + user_roles
        for email, full_name, pw, org_id, role_name in USERS:
            s.execute(text("""
                INSERT INTO users (user_id, org_id, email, role, full_name, hashed_password, status, created_at)
                VALUES (gen_random_uuid(), :o, :e, :r, :fn, :hp, 'active', now())
                ON CONFLICT (org_id, email) DO UPDATE
                   SET full_name = EXCLUDED.full_name,
                       hashed_password = EXCLUDED.hashed_password,
                       status = 'active',
                       role = EXCLUDED.role
            """), {"o": org_id, "e": email, "r": role_name, "fn": full_name,
                   "hp": hash_password(pw)})
            user_id = s.execute(text(
                "SELECT user_id FROM users WHERE org_id = :o AND email = :e"
            ), {"o": org_id, "e": email}).scalar()
            role_id = s.execute(text(
                "SELECT role_id FROM roles WHERE org_id = :o AND name = :n"
            ), {"o": org_id, "n": role_name}).scalar()
            if role_id is None:
                raise SystemExit(f"role {role_name!r} does not exist for {email}'s organisation — fix the USERS table")
            s.execute(text("""
                INSERT INTO user_roles (user_id, role_id) VALUES (:u, :r)
                ON CONFLICT DO NOTHING
            """), {"u": user_id, "r": role_id})
            for extra in EXTRA_USER_ROLES.get(email, []):
                s.execute(text("""
                    INSERT INTO user_roles (user_id, role_id)
                    SELECT :u, role_id FROM roles WHERE org_id = :o AND name = :n ON CONFLICT DO NOTHING
                """), {"u": user_id, "o": org_id, "n": extra})

        # 5) supervision scope + profile: one body per sector; any scope row now outside a body's profile ends
        for reg_id, (profile, _slug, scope) in SUPERVISORS.items():
            s.execute(text("""
                INSERT INTO supervisor_settings (org_id, profile, thresholds) VALUES (CAST(:o AS uuid), :p, '{}'::jsonb)
                ON CONFLICT (org_id) DO UPDATE SET profile = EXCLUDED.profile
            """), {"o": reg_id, "p": profile})
            for supervised, juris in scope:
                s.execute(text("""
                    INSERT INTO supervision_scope (regulator_org_id, supervised_org_id, jurisdiction, active)
                    VALUES (CAST(:r AS uuid), CAST(:s AS uuid), :j, TRUE)
                    ON CONFLICT (regulator_org_id, supervised_org_id) DO UPDATE
                       SET jurisdiction = EXCLUDED.jurisdiction, active = TRUE, ended_at = NULL
                """), {"r": reg_id, "s": supervised, "j": juris})
            s.execute(text("""
                UPDATE supervision_scope SET active = FALSE, ended_at = COALESCE(ended_at, now())
                WHERE regulator_org_id = CAST(:r AS uuid) AND active AND supervised_org_id <> ALL(CAST(:keep AS uuid[]))
            """), {"r": reg_id, "keep": [x for x, _ in scope]})

        # 6) assignments: the line supervisor (approver persona) works two of the four; horizontal roles see all
        for email, supervised, cap in [("approver@supervisor.demo", MERIDIAN, "lead"), ("approver@insurance-supervisor.demo", IBERIA, "lead"),
                                       ("approver@markets-supervisor.demo", STELLAR, "lead")]:
            s.execute(text("""
                INSERT INTO supervision_assignment (regulator_org_id, supervised_org_id, user_id, capacity)
                SELECT CAST(:r AS uuid), CAST(:s AS uuid), u.user_id, :c FROM users u WHERE u.email = :e
                  AND NOT EXISTS (SELECT 1 FROM supervision_assignment a WHERE a.regulator_org_id = CAST(:r AS uuid)
                                  AND a.supervised_org_id = CAST(:s AS uuid) AND a.user_id = u.user_id AND a.revoked_at IS NULL)
            """), {"r": next(k for k, v in SUPERVISORS.items() if any(x == supervised for x, _ in v[2])), "s": supervised, "c": cap, "e": email})
        # an assignment to an entity outside the body's scope ends with it
        s.execute(text("""UPDATE supervision_assignment a SET revoked_at = now() WHERE revoked_at IS NULL AND NOT EXISTS
                          (SELECT 1 FROM supervision_scope ss WHERE ss.regulator_org_id = a.regulator_org_id
                           AND ss.supervised_org_id = a.supervised_org_id AND ss.active)"""))

        n_users = s.execute(text("SELECT count(*) FROM users WHERE hashed_password IS NOT NULL")).scalar()
        n_roles = s.execute(text("SELECT count(*) FROM roles")).scalar()
        n_ent   = s.execute(text("SELECT count(*) FROM org_entitlements")).scalar()
        print(f"seeded {len(USERS)} demo users (total with passwords: {n_users}), "
              f"{n_roles} roles, {n_ent} entitlements across {len(ORGS)} orgs")
        print("login e.g.:  admin@meridian.demo / Demo!admin1")


if __name__ == "__main__":
    main()
