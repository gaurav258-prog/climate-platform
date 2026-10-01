"""The development database's migrations are the files as they are (E100): every revision applied to it was applied
from a file with the same content it has now. A migration edited after it ran here (e.g. applied by the API's start-up
migration while it was still being written) leaves the schema unlike the file — refused with what to do.

  venv/bin/python -m scripts.check_applied_migrations
"""
from __future__ import annotations

import hashlib
import sys

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

from core.db.config import DATABASE_URL


def main() -> int:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    eng = create_engine(DATABASE_URL)
    with eng.connect() as c:
        if not c.execute(text("SELECT 1 FROM information_schema.tables WHERE table_schema = 'migration_meta' "
                              "AND table_name = 'applied_file'")).first():
            print("applied-migration check: no record yet (applied before E100) — nothing to compare")
            return 0
        rows = c.execute(text("SELECT revision, sha256 FROM migration_meta.applied_file")).all()
    bad = []
    for rev, sha in rows:
        r = script.get_revision(rev)
        if r is None:
            bad.append(f"{rev}: applied here but its file no longer exists")
            continue
        with open(r.path, "rb") as f:
            if hashlib.sha256(f.read()).hexdigest() != sha:
                bad.append(f"{rev}: its file changed after it was applied to this database — downgrade below it with the "
                           "version that ran (git stash), then upgrade again; or rebuild the dev database")
    if bad:
        print("applied-migration check FAILED:\n  " + "\n  ".join(bad))
        return 1
    print(f"applied-migration check OK — {len(rows)} revisions match their files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
