"""Seed the Tellumen platform tenant + a platform-operator user (cross-tenant console).

Idempotent. Creates:
  - a 'Tellumen (platform)' organization (type='platform') — the home org for staff accounts,
  - a 'platform-operator' role holding platform.admin + portal.use,
  - ops@tellumen.io / Demo!ops1 with that role.

The operator is the ONLY account that can read the cross-tenant /v1/ops console.
Run: .venv/bin/python -m scripts.seed_platform_operator
"""
import uuid

from sqlalchemy import text

from core.db.session import SessionLocal
from api.security import hash_password

PLATFORM_ORG = "99999999-9999-4999-8999-999999999999"


def main() -> None:
    s = SessionLocal()
    # 1) platform org
    s.execute(text("""
        INSERT INTO organizations (org_id, name, type, country)
        VALUES (:o, 'Tellumen (platform)', 'platform', 'EU')
        ON CONFLICT (org_id) DO NOTHING
    """), {"o": PLATFORM_ORG})

    # 2) platform-operator role + perms
    rid = s.execute(text("SELECT role_id FROM roles WHERE org_id=:o AND name='platform-operator'"), {"o": PLATFORM_ORG}).scalar()
    if not rid:
        rid = str(uuid.uuid4())
        s.execute(text("INSERT INTO roles (role_id, org_id, name, description, is_system) VALUES (:r,:o,'platform-operator','Tellumen staff — cross-tenant operator',true)"),
                  {"r": rid, "o": PLATFORM_ORG})
    s.execute(text("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT :r, permission_id FROM permissions WHERE code = ANY(:c) ON CONFLICT DO NOTHING
    """), {"r": str(rid), "c": ["platform.admin", "portal.use"]})

    # 3) operator user
    uid = s.execute(text("SELECT user_id FROM users WHERE email='ops@tellumen.io'")).scalar()
    if not uid:
        uid = str(uuid.uuid4())
        s.execute(text("""
            INSERT INTO users (user_id, org_id, email, role, full_name, hashed_password, status, created_at)
            VALUES (:i,:o,'ops@tellumen.io','platform-operator','Otto Operator (Tellumen)',:h,'active',now())
        """), {"i": uid, "o": PLATFORM_ORG, "h": hash_password("Demo!ops1")})
    s.execute(text("INSERT INTO user_roles (user_id, role_id) VALUES (:u,:r) ON CONFLICT DO NOTHING"), {"u": str(uid), "r": str(rid)})
    s.commit()
    perms = s.execute(text("""
        SELECT array_agg(DISTINCT p.code) FROM users u JOIN user_roles ur ON ur.user_id=u.user_id
        JOIN role_permissions rp ON rp.role_id=ur.role_id JOIN permissions p ON p.permission_id=rp.permission_id
        WHERE u.email='ops@tellumen.io'
    """)).scalar()
    print("seeded ops@tellumen.io / Demo!ops1 · perms:", sorted(perms or []))


if __name__ == "__main__":
    main()
