"""The development database's migrations are the files as they are (E100): every revision applied to it was applied
from a file with the same content it has now. A migration edited after it ran here (e.g. applied by the API's start-up
migration while it was still being written) leaves the schema unlike the file — refused with what to do. An edit confined
to the migration's REFUSAL_PROBE (a round-trip fixture that never runs on upgrade or downgrade) is not a change to what
it built: compared on core.db.migration_fingerprint.schema_sha (E172).

  venv/bin/python -m scripts.check_applied_migrations
"""
from __future__ import annotations

import sys

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

from core.db.config import DATABASE_URL
from core.db.migration_fingerprint import file_sha, schema_sha


def main() -> int:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    eng = create_engine(DATABASE_URL)
    with eng.connect() as c:
        if not c.execute(text("SELECT 1 FROM information_schema.tables WHERE table_schema = 'migration_meta' "
                              "AND table_name = 'applied_file'")).first():
            print("applied-migration check: no record yet (applied before E100) — nothing to compare")
            return 0
        c.execute(text("ALTER TABLE migration_meta.applied_file ADD COLUMN IF NOT EXISTS schema_sha256 TEXT"))
        rows = c.execute(text("SELECT revision, sha256, schema_sha256 FROM migration_meta.applied_file")).all()
        bad, filled = [], 0
        for rev, sha, schema in rows:
            r = script.get_revision(rev)
            if r is None:
                bad.append(f"{rev}: applied here but its file no longer exists")
                continue
            if file_sha(r.path) == sha:
                if schema is None:      # the file is exactly the one that ran: its probe-free fingerprint is known
                    c.execute(text("UPDATE migration_meta.applied_file SET schema_sha256 = :m WHERE revision = :r"),
                              {"m": schema_sha(r.path), "r": rev})
                    filled += 1
                continue
            if schema is not None and schema_sha(r.path) == schema:
                continue                # only its REFUSAL_PROBE changed: the schema it built is the file's (E172)
            bad.append(f"{rev}: its file changed after it was applied to this database — downgrade below it with the "
                       "version that ran (git stash), then upgrade again; or rebuild the dev database")
        c.commit()
    if bad:
        print("applied-migration check FAILED:\n  " + "\n  ".join(bad))
        return 1
    print(f"applied-migration check OK — {len(rows)} revisions match their files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
