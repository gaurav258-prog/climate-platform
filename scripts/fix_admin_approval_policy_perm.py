"""Grant admin.approval_policy.manage to every 'admin' role that's missing it — a seed-drift fix.

The approval matrix (which actions need 4-eyes, incl. forward-risk decisions) is the org admin's onboarding
control, gated by admin.approval_policy.manage. Some demo orgs' admin role had it and others didn't, so those
admins couldn't reach the matrix. This makes the admin role consistent. Idempotent.
"""
from __future__ import annotations

from sqlalchemy import text

from core.db.session import SessionLocal


def run() -> None:
    s = SessionLocal()
    try:
        pid = s.execute(text("SELECT permission_id FROM permissions WHERE code = 'admin.approval_policy.manage'")).scalar()
        if not pid:
            print("permission admin.approval_policy.manage not found — nothing to do")
            return
        res = s.execute(text("""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.role_id, :p FROM roles r
            WHERE r.name = 'admin'
              AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.role_id AND rp.permission_id = :p)
        """), {"p": pid})
        s.commit()
        print(f"granted admin.approval_policy.manage to {res.rowcount} admin role(s)")
    finally:
        s.close()


if __name__ == "__main__":
    run()
