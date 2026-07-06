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

Run:  .venv/bin/python scripts/seed_auth_demo.py
"""
from sqlalchemy import text

from core.db.session import get_session
from api.security import hash_password

MERIDIAN = "11111111-1111-4111-8111-111111111111"
IBERIA   = "22222222-2222-4222-8222-222222222222"
STELLAR  = "33333333-3333-4333-8333-333333333333"

ORGS = [
    # org_id, name, type, country, aum_eur, employees
    (MERIDIAN, "Meridian Bank (demo)", "bank",     "ES", 48_000_000_000, 4200),
    (IBERIA,   "Iberia Mutual (demo)", "insurer",  "ES", 12_000_000_000, 1800),
    (STELLAR,  "Stellar Logistics REIT (demo)", "reit", "NL", 3_600_000_000, 210),
]

ENTITLEMENTS = {
    MERIDIAN: ["physical-risk", "reporting", "trust"],
    IBERIA:   ["underwriting", "parametric"],
    STELLAR:  ["portfolio-risk"],
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

# email, full_name, password, org_id, role
USERS = [
    ("admin@meridian.demo",    "Mara Admin (Meridian)",    "Demo!admin1",   MERIDIAN, "admin"),
    ("analyst@meridian.demo",  "Ana Analyst (Meridian)",   "Demo!analyst1", MERIDIAN, "analyst"),
    ("approver@meridian.demo", "Pieter Approver (Meridian)", "Demo!approve1", MERIDIAN, "approver"),
    ("admin@iberia.demo",      "Iria Admin (Iberia)",      "Demo!admin1",   IBERIA,   "admin"),
    ("analyst@iberia.demo",    "Alba Analyst (Iberia)",    "Demo!analyst1", IBERIA,   "analyst"),
    ("admin@stellar.demo",     "Sven Admin (Stellar)",     "Demo!admin1",   STELLAR,  "admin"),
    ("analyst@stellar.demo",   "Sanne Analyst (Stellar)",  "Demo!analyst1", STELLAR,  "analyst"),
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
            for role_name, perms in ROLE_PERMS.items():
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
                for code in perms:
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
            s.execute(text("""
                INSERT INTO user_roles (user_id, role_id) VALUES (:u, :r)
                ON CONFLICT DO NOTHING
            """), {"u": user_id, "r": role_id})

        n_users = s.execute(text("SELECT count(*) FROM users WHERE hashed_password IS NOT NULL")).scalar()
        n_roles = s.execute(text("SELECT count(*) FROM roles")).scalar()
        n_ent   = s.execute(text("SELECT count(*) FROM org_entitlements")).scalar()
        print(f"seeded {len(USERS)} demo users (total with passwords: {n_users}), "
              f"{n_roles} roles, {n_ent} entitlements across {len(ORGS)} orgs")
        print("login e.g.:  admin@meridian.demo / Demo!admin1")


if __name__ == "__main__":
    main()
