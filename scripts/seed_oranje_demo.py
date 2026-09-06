"""Seed the acceptance-test tenant: Oranje Foods NV (demo) — a ~€100bn NL-HQ global food supplier
(manufacturer sector). Idempotent. Creates the org, RBAC roles, three demo users, and agri entitlements,
reusing the same role/permission matrix as the other demo tenants. Commodities are the shared global master
(sc_commodities), so nothing extra is needed there.

Run:  .venv/bin/python -m scripts.seed_oranje_demo
"""
from __future__ import annotations

from sqlalchemy import text

from api.security import hash_password
from core.db.session import get_session
from scripts.seed_auth_demo import EXTRA_ROLE_PERMS, ROLE_PERMS

ORANJE = "66666666-6666-4666-8666-666666666666"
USERS = [
    ("admin@oranje.demo",    "Anna Admin (Oranje Foods)",    "Demo!admin1",   "admin"),
    ("analyst@oranje.demo",  "Aart Analyst (Oranje Foods)",  "Demo!analyst1", "analyst"),
    ("approver@oranje.demo", "Bram Approver (Oranje Foods)", "Demo!approve1", "approver"),
]
ENTITLEMENTS = ["physical-risk", "reporting", "supply-chain", "trust"]


def main() -> int:
    with get_session() as s:
        s.execute(text("""
            INSERT INTO organizations (org_id, name, type, country, aum_eur, employees, created_at, updated_at)
            VALUES (CAST(:o AS uuid), :n, 'manufacturer', 'NL', :rev, 12500, now(), now())
            ON CONFLICT (org_id) DO UPDATE SET name = EXCLUDED.name, type = EXCLUDED.type
        """), {"o": ORANJE, "n": "Oranje Foods NV (demo)", "rev": 100_000_000_000})

        for off in ENTITLEMENTS:
            s.execute(text("""INSERT INTO org_entitlements (org_id, offering_id, enabled)
                              VALUES (CAST(:o AS uuid), :off, true)
                              ON CONFLICT (org_id, offering_id) DO UPDATE SET enabled = true"""),
                      {"o": ORANJE, "off": off})

        for role_name, perms in ROLE_PERMS.items():
            s.execute(text("""INSERT INTO roles (org_id, name, description, is_system)
                              VALUES (CAST(:o AS uuid), :n, :d, true) ON CONFLICT DO NOTHING"""),
                      {"o": ORANJE, "n": role_name, "d": f"{role_name} role"})
            role_id = s.execute(text("SELECT role_id FROM roles WHERE org_id = CAST(:o AS uuid) AND name = :n"),
                                {"o": ORANJE, "n": role_name}).scalar()
            s.execute(text("DELETE FROM role_permissions WHERE role_id = :r"), {"r": role_id})
            for code in perms + EXTRA_ROLE_PERMS.get(role_name, []):
                s.execute(text("""INSERT INTO role_permissions (role_id, permission_id)
                                  SELECT :r, permission_id FROM permissions WHERE code = :c
                                  ON CONFLICT DO NOTHING"""), {"r": role_id, "c": code})

        for email, full_name, pw, role_name in USERS:
            s.execute(text("""
                INSERT INTO users (user_id, org_id, email, role, full_name, hashed_password, status, created_at)
                VALUES (gen_random_uuid(), CAST(:o AS uuid), :e, :r, :fn, :hp, 'active', now())
                ON CONFLICT (org_id, email) DO UPDATE SET hashed_password = EXCLUDED.hashed_password, status='active', role=EXCLUDED.role
            """), {"o": ORANJE, "e": email, "r": role_name, "fn": full_name, "hp": hash_password(pw)})
            uid = s.execute(text("SELECT user_id FROM users WHERE org_id = CAST(:o AS uuid) AND email = :e"),
                            {"o": ORANJE, "e": email}).scalar()
            rid = s.execute(text("SELECT role_id FROM roles WHERE org_id = CAST(:o AS uuid) AND name = :n"),
                            {"o": ORANJE, "n": role_name}).scalar()
            s.execute(text("INSERT INTO user_roles (user_id, role_id) VALUES (:u, :r) ON CONFLICT DO NOTHING"),
                      {"u": uid, "r": rid})
        s.commit()
    print("seeded Oranje Foods NV (demo) — login admin@oranje.demo / Demo!admin1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
