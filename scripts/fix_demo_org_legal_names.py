"""Fix demo orgs whose legal_name was pulled from a real (unrelated) GLEIF LEI — e.g. the demo bank read
'Andre Niermann automotive electrical products GmbH' and the demo asset manager read 'AMUNDI ASSET
MANAGEMENT'. Sets each demo org's legal_name to its own demo entity name so the filing identity + SFDR
statements read correctly per sector. Idempotent; leaves not-yet-configured orgs (legal_name NULL) alone.
"""
from __future__ import annotations

from sqlalchemy import text

from core.db.session import SessionLocal


def run() -> None:
    s = SessionLocal()
    try:
        res = s.execute(text(r"""
            UPDATE organizations
            SET    legal_name = regexp_replace(name, '\s*\(demo\)\s*$', ''), updated_at = now()
            WHERE  name LIKE '%(demo)'
              AND  legal_name IS NOT NULL
              AND  legal_name <> regexp_replace(name, '\s*\(demo\)\s*$', '')
            RETURNING name, legal_name
        """))
        rows = res.fetchall()
        s.commit()
        for name, legal in rows:
            print(f"  {name} → legal_name '{legal}'")
        print(f"done · {len(rows)} org(s) corrected" if rows else "nothing to fix (already correct)")
    finally:
        s.close()


if __name__ == "__main__":
    run()
