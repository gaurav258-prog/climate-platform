"""Every migration can be undone, exactly — checked step by step on a scratch database (error log E25).

Builds a throw-away database from nothing, one revision at a time, recording the schema after each step. Then walks
back down one revision at a time: every downgrade must run, and must leave exactly the schema recorded for the
revision it returns to (tables, columns, constraints, indexes, views, functions, triggers). Finally it builds back up
to head and requires the head schema to match the first build. So a downgrade that fails, or that "succeeds" but puts
something back differently from how it was, is named with its revision. (Columns are compared by name, type,
nullability and default — not position: Postgres cannot put a re-added column back in its old place, and the
application always addresses columns by name.)

The live database is never touched. The scratch database is created and dropped with an administrative connection
(MIGCHECK_ADMIN_URL, default: the local superuser via the socket) and owned by the application's role (from
DATABASE_URL), so the migrations themselves run with the application's own privileges.

    venv/bin/python -m scripts.check_migration_roundtrip          (exit 0 = ok)
"""
from __future__ import annotations

import logging
import os
import sys
import time

import psycopg
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

ROOT = os.path.join(os.path.dirname(__file__), "..")
SCRATCH = os.environ.get("MIGCHECK_DB", "climate_migcheck")

_SNAPSHOT_SQL = {
    "column": """SELECT table_name || '.' || column_name || ' ' || data_type || COALESCE('(' || character_maximum_length || ')', '')
                        || COALESCE('(' || numeric_precision || ',' || numeric_scale || ')', '') || ' ' || is_nullable || ' ' ||
                        COALESCE(column_default, '')
                 FROM information_schema.columns WHERE table_schema = 'public'""",
    "constraint": """SELECT c.conrelid::regclass || ' ' || c.conname || ' ' || pg_get_constraintdef(c.oid)
                     FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace WHERE n.nspname = 'public'""",
    "index": "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public'",
    "view": """SELECT c.relname || ' ' || c.relkind::text || ' ' || pg_get_viewdef(c.oid, true) FROM pg_class c
               JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind IN ('v', 'm')""",
    "function": """SELECT pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                   WHERE n.nspname = 'public' AND p.prokind IN ('f', 'p')""",
    "trigger": """SELECT tgrelid::regclass || ' ' || pg_get_triggerdef(t.oid) FROM pg_trigger t
                  JOIN pg_class c ON c.oid = t.tgrelid JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = 'public' AND NOT t.tgisinternal""",
}


def _snapshot(conn) -> frozenset[str]:
    """The schema as a set of normalised lines — alembic's own version table excluded (it stays at base)."""
    out = set()
    for kind, sql in _SNAPSHOT_SQL.items():
        out |= {f"{kind}: {' '.join(str(r[0]).split())}" for r in conn.execute(sql).fetchall()}
    return frozenset(x for x in out if "alembic_version" not in x)


def _heads(conn) -> frozenset[str]:
    try:
        return frozenset(r[0] for r in conn.execute("SELECT version_num FROM alembic_version").fetchall())
    except psycopg.errors.UndefinedTable:
        conn.rollback()
        return frozenset()


def _diff(want: frozenset[str], got: frozenset[str]) -> list[str]:
    return [f"  missing  {x[:220]}" for x in sorted(want - got)] + [f"  extra    {x[:220]}" for x in sorted(got - want)]


def _fresh_database(admin: str, owner: str) -> None:
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")
        a.execute(f'CREATE DATABASE {SCRATCH} OWNER "{owner}"')


def main() -> int:
    app_url = make_url(os.environ.get("DATABASE_URL") or _app_database_url())
    scratch_url = app_url.set(database=SCRATCH)
    admin = os.environ.get("MIGCHECK_ADMIN_URL", "postgresql:///postgres")
    _fresh_database(admin, app_url.username)

    cfg = Config(os.path.join(ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(ROOT, "core", "db", "migrations"))
    os.environ["DATABASE_URL"] = scratch_url.render_as_string(hide_password=False)
    plain = scratch_url.set(drivername="postgresql").render_as_string(hide_password=False)
    logging.disable(logging.WARNING)
    t0 = time.time()
    failures: list[str] = []
    script = ScriptDirectory.from_config(cfg)
    order = [r.revision for r in reversed(list(script.walk_revisions()))]
    rank = {rev: k for k, rev in enumerate(order)}
    try:
        conn = psycopg.connect(plain, autocommit=True)
        snapshots = {_heads(conn): _snapshot(conn)}
        state_before: dict[str, frozenset[str]] = {}
        for rev in order:                                          # up, one revision at a time (topological order)
            state_before[rev] = _heads(conn)
            try:
                command.upgrade(cfg, rev)
            except Exception as e:                                 # noqa: BLE001 — an upgrade that cannot run is the finding
                failures.append(f"upgrade to {rev} failed: {type(e).__name__}: {str(e).splitlines()[0]}")
                return _report(failures, t0)
            now = _heads(conn)
            if now in snapshots:                                    # each state must be reached once, by one path
                failures.append(f"upgrade to {rev} left the version table at {sorted(now)}, a state already passed")
                return _report(failures, t0)
            snapshots[now] = _snapshot(conn)
        head, head_schema = _heads(conn), _snapshot(conn)
        print(f"built {len(order)} revisions up to {sorted(head)}")

        while at := _heads(conn):                                  # down: undo the newest head, mirroring the way up
            newest = max(at, key=rank.__getitem__)
            want = state_before[newest]
            problem = None
            try:
                parents = script.get_revision(newest).down_revision
                # a merge has several parents: name one — undoing the merge leaves every parent as a head
                command.downgrade(cfg, parents[0] if isinstance(parents, tuple) else f"{newest}@-1")
                if _heads(conn) != want:
                    problem = f"downgrade of {newest} left the version table at {sorted(_heads(conn))}, not {sorted(want)}"
                elif d := _diff(snapshots[want], _snapshot(conn)):
                    problem = (f"downgrade of {newest} does not restore the schema of {sorted(want) or 'base'}:\n"
                               + "\n".join(d[:12]) + (f"\n  … {len(d) - 12} more" if len(d) > 12 else ""))
            except Exception as e:                                 # noqa: BLE001
                problem = f"downgrade of {newest} failed: {type(e).__name__}: {str(e).splitlines()[0]}"
            if problem:
                # record it, then carry on from a clean build of the state the downgrade should have reached, so
                # one run names every defective downgrade (a drifted start would blame the wrong later steps)
                failures.append(problem)
                conn.close()
                _fresh_database(admin, app_url.username)
                for h in sorted(want, key=rank.__getitem__):
                    command.upgrade(cfg, h)
                conn = psycopg.connect(plain, autocommit=True)

        command.upgrade(cfg, "head")                               # and back up: the same head schema
        if d := _diff(head_schema, _snapshot(conn)):
            failures.append("rebuilding to head after a full downgrade gives a different schema:\n" + "\n".join(d[:12]))
        conn.close()
    finally:
        with psycopg.connect(admin, autocommit=True) as a:
            a.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")
    return _report(failures, t0)


def _app_database_url() -> str:
    from core.config import settings
    return settings.DATABASE_URL


def _report(failures: list[str], t0: float) -> int:
    if failures:
        print("MIGRATION ROUND-TRIP FAILED\n" + "\n".join(failures))
        return 1
    print(f"migration round-trip ok — every revision up and down, schema restored exactly ({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
