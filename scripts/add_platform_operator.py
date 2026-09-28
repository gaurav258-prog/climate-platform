"""Add a named Tellumen staff member as a platform operator, who then sets their own password.

The account is created without a password; a one-time set-password link (valid RESET_TTL_HOURS) is printed, so no one
else ever chooses or sees it. Needs the platform tenant and role (scripts/seed_platform_operator.py). Idempotent on email.

Run: venv/bin/python -m scripts.add_platform_operator --email you@example.com --name "Full Name"
"""
import argparse
import secrets
import uuid
from datetime import timedelta

from sqlalchemy import text

from core.config import settings
from core.db.session import SessionLocal
from scripts.seed_platform_operator import PLATFORM_ORG
from services.governance.account_security import RESET_TTL_HOURS, _hash, _now


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--name", required=True)
    a = ap.parse_args()
    email = a.email.strip().lower()
    s = SessionLocal()
    rid = s.execute(text("SELECT role_id FROM roles WHERE org_id = :o AND name = 'platform-operator'"), {"o": PLATFORM_ORG}).scalar()
    if not rid:
        raise SystemExit("no platform-operator role — run scripts.seed_platform_operator first")
    uid = s.execute(text("SELECT user_id FROM users WHERE org_id = :o AND lower(email) = :e"), {"o": PLATFORM_ORG, "e": email}).scalar()
    if not uid:
        uid = str(uuid.uuid4())
        s.execute(text("""INSERT INTO users (user_id, org_id, email, role, full_name, hashed_password, status, created_at)
                          VALUES (:i, :o, :e, 'platform-operator', :n, NULL, 'active', now())"""),
                  {"i": uid, "o": PLATFORM_ORG, "e": email, "n": a.name.strip()})
    s.execute(text("INSERT INTO user_roles (user_id, role_id) VALUES (:u, :r) ON CONFLICT DO NOTHING"), {"u": str(uid), "r": str(rid)})
    raw = secrets.token_urlsafe(32)
    s.execute(text("""INSERT INTO password_reset (reset_id, user_id, token_hash, status, expires_at)
                      VALUES (CAST(:i AS uuid), CAST(:u AS uuid), :h, 'pending', :exp)"""),
              {"i": str(uuid.uuid4()), "u": str(uid), "h": _hash(raw), "exp": _now() + timedelta(hours=RESET_TTL_HOURS)})
    s.commit()
    print(f"platform operator: {a.name.strip()} <{email}>")
    print(f"set your password (valid {RESET_TTL_HOURS}h): {settings.APP_BASE_URL.rstrip('/')}/reset/{raw}")


if __name__ == "__main__":
    main()
