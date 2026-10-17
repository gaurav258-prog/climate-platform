"""The schema as PostgreSQL's catalogue states it, read from a database the migrations build to head.

The document describes what the code produces, so the gate never reads the development database (it may hold another
session's migration, or one applied while still being written — E28, E100): it builds a scratch database from the
migration files, the same way scripts/check_migration_roundtrip.py does, reads the catalogue, and drops it.
`read_catalogue` takes any open connection, so `--database` can point the generator at an existing database for a
quick look; the gate never does.
"""
from __future__ import annotations

import logging
import os
import re
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# user schemas only — PostgreSQL's own and TimescaleDB's internal ones (present only where it is installed) excluded
_MINE = ("n.nspname NOT LIKE 'pg\\_%' AND n.nspname <> 'information_schema' "
         "AND n.nspname NOT LIKE '\\_timescaledb%' AND n.nspname NOT LIKE 'timescaledb%'")

_SQL = {
    "relations": f"""
        SELECT n.nspname, c.relname, c.relkind, obj_description(c.oid, 'pg_class'), c.relrowsecurity
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind IN ('r', 'p', 'v', 'm') AND {_MINE}""",
    "columns": f"""
        SELECT n.nspname, c.relname, a.attnum, a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull,
               pg_get_expr(d.adbin, d.adrelid), col_description(c.oid, a.attnum), a.attidentity, a.attgenerated
        FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
        WHERE c.relkind IN ('r', 'p', 'v', 'm') AND a.attnum > 0 AND NOT a.attisdropped AND {_MINE}""",
    "constraints": f"""
        SELECT n.nspname, c.relname, k.conname, k.contype, pg_get_constraintdef(k.oid),
               ARRAY(SELECT a.attname FROM unnest(k.conkey) WITH ORDINALITY u(num, ord)
                     JOIN pg_attribute a ON a.attrelid = k.conrelid AND a.attnum = u.num ORDER BY u.ord),
               fn.nspname, fc.relname,
               ARRAY(SELECT a.attname FROM unnest(k.confkey) WITH ORDINALITY u(num, ord)
                     JOIN pg_attribute a ON a.attrelid = k.confrelid AND a.attnum = u.num ORDER BY u.ord),
               k.confdeltype, k.confupdtype
        FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_class fc ON fc.oid = k.confrelid LEFT JOIN pg_namespace fn ON fn.oid = fc.relnamespace
        WHERE {_MINE}""",
    "indexes": f"""
        SELECT n.nspname, c.relname, ic.relname, pg_get_indexdef(i.indexrelid), i.indisunique
        FROM pg_index i JOIN pg_class c ON c.oid = i.indrelid JOIN pg_class ic ON ic.oid = i.indexrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE {_MINE} AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conindid = i.indexrelid)""",
    "triggers": f"""
        SELECT n.nspname, c.relname, t.tgname, pg_get_triggerdef(t.oid), pn.nspname || '.' || p.proname, p.prosrc
        FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_proc p ON p.oid = t.tgfoid JOIN pg_namespace pn ON pn.oid = p.pronamespace
        WHERE NOT t.tgisinternal AND {_MINE}""",
    "view_reads": f"""
        SELECT DISTINCT n.nspname, v.relname, tn.nspname, t.relname
        FROM pg_depend d JOIN pg_rewrite r ON r.oid = d.objid JOIN pg_class v ON v.oid = r.ev_class
        JOIN pg_namespace n ON n.oid = v.relnamespace JOIN pg_class t ON t.oid = d.refobjid
        JOIN pg_namespace tn ON tn.oid = t.relnamespace
        WHERE d.classid = 'pg_rewrite'::regclass AND d.refclassid = 'pg_class'::regclass AND t.oid <> v.oid
          AND t.relkind IN ('r', 'p', 'v', 'm') AND {_MINE}""",
    "functions": f"""
        SELECT n.nspname, p.proname, pg_get_function_arguments(p.oid), pg_get_function_result(p.oid)
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE p.prokind IN ('f', 'p') AND {_MINE}
          AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = p.oid AND d.deptype = 'e')""",
    "policies": "SELECT schemaname, tablename, policyname FROM pg_policies",
    "extensions": "SELECT extname FROM pg_extension",
}

_FK_ACTION = {"a": "no action", "r": "restrict", "c": "cascade", "n": "set null", "d": "set default"}


def _raises(src: str) -> list[str]:
    """The literal messages a PL/pgSQL body raises as exceptions (a message built at run time is named as such)."""
    if not re.search(r"RAISE\s+EXCEPTION", src, re.I):
        return []
    found = [m.replace("''", "'") for m in re.findall(r"RAISE\s+EXCEPTION\s+'((?:[^']|'')*)'", src, re.I)]
    return sorted(set(found)) or ["(message built at run time)"]


def read_catalogue(conn) -> dict:
    """Everything the document states, as plain data (JSON-able), from one open psycopg connection."""
    q = {k: conn.execute(sql).fetchall() for k, sql in _SQL.items()}
    rel: dict[str, dict] = {}
    for schema, name, kind, comment, rls in q["relations"]:
        rel[f"{schema}.{name}"] = {"kind": "table" if kind in "rp" else "view", "comment": comment or "", "rls": rls,
                                   "columns": [], "pk": [], "uniques": [], "fks": [], "checks": [], "excludes": [],
                                   "indexes": [], "triggers": [], "reads": []}
    for schema, name, num, col, typ, notnull, default, comment, identity, generated in sorted(q["columns"]):
        rel[f"{schema}.{name}"]["columns"].append({
            "name": col, "type": typ, "nullable": not notnull, "default": default or "", "comment": comment or "",
            "identity": {"a": "always", "d": "by default"}.get(identity, ""), "generated": generated == "s"})
    for schema, name, con, ctype, definition, cols, fschema, ftable, fcols, ondel, onupd in q["constraints"]:
        r = rel[f"{schema}.{name}"]
        if ctype == "p":
            r["pk"] = list(cols)
        elif ctype == "u":
            r["uniques"].append({"name": con, "columns": list(cols)})
        elif ctype == "f":
            r["fks"].append({"name": con, "columns": list(cols), "ref": f"{fschema}.{ftable}", "ref_columns": list(fcols),
                             "on_delete": _FK_ACTION[ondel], "on_update": _FK_ACTION[onupd]})
        elif ctype == "c":
            r["checks"].append({"name": con, "definition": definition})
        elif ctype == "x":
            r["excludes"].append({"name": con, "definition": definition})
    for schema, name, index, definition, unique in q["indexes"]:
        rel[f"{schema}.{name}"]["indexes"].append({"name": index, "definition": definition, "unique": unique})
    for schema, name, trig, definition, function, src in q["triggers"]:
        m = re.search(r"\b(BEFORE|AFTER|INSTEAD OF)\s+(.+?)\s+ON\s", definition)
        rel[f"{schema}.{name}"]["triggers"].append({
            "name": trig, "timing": m.group(1) if m else "", "events": m.group(2) if m else "",
            "per": "row" if "FOR EACH ROW" in definition else "statement", "function": function,
            "raises": _raises(src or ""), "definition": definition})
    for schema, view, tschema, table in q["view_reads"]:
        rel[f"{schema}.{view}"]["reads"].append(f"{tschema}.{table}")
    for r in rel.values():
        for key in ("uniques", "fks", "checks", "excludes", "indexes", "triggers"):
            r[key].sort(key=lambda x: x["name"])
        r["reads"].sort()
    permissions = []
    if "public.permissions" in rel:
        permissions = [list(x) for x in conn.execute(
            "SELECT code, COALESCE(description, '') FROM permissions ORDER BY code").fetchall()]
    return {"relations": dict(sorted(rel.items())),
            "functions": sorted([f"{s}.{n}({a}) → {r}" for s, n, a, r in q["functions"] if r != "trigger"]),
            "policies": sorted(f"{s}.{t}: {p}" for s, t, p in q["policies"]),
            "extensions": sorted(x for (x,) in q["extensions"]),
            "permissions": permissions}


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@contextmanager
def head_database():
    """A scratch database the migration files build to head; yields its psycopg URL, drops it afterwards.

    Named <MIGCHECK_DB>_docs_<pid> (one per run, E33), created and dropped through MIGCHECK_ADMIN_URL (default: the
    local superuser via the socket) and owned by the application's role, as check_migration_roundtrip does."""
    import psycopg
    from alembic import command
    from alembic.config import Config
    from sqlalchemy.engine import make_url

    from core.config import settings

    app = make_url(os.environ.get("DATABASE_URL") or settings.DATABASE_URL)
    prefix = os.environ.get("MIGCHECK_DB", "climate_migcheck")
    name = f"{prefix}_docs_{os.getpid()}"
    admin = os.environ.get("MIGCHECK_ADMIN_URL", "postgresql:///postgres")
    with psycopg.connect(admin, autocommit=True) as a:
        for (old,) in a.execute("SELECT datname FROM pg_database WHERE datname LIKE %s",
                                (f"{prefix}\\_docs\\_%",)).fetchall():
            tail = old.rsplit("_", 1)[-1]
            if tail.isdigit() and not _alive(int(tail)):              # left by a run that was killed
                a.execute(f'DROP DATABASE IF EXISTS "{old}" WITH (FORCE)')
        a.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        a.execute(f'CREATE DATABASE "{name}" OWNER "{app.username}"')
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "core" / "db" / "migrations"))
    before = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = app.set(database=name).render_as_string(hide_password=False)
    try:
        logging.disable(logging.WARNING)
        command.upgrade(cfg, "head")
        logging.disable(logging.NOTSET)
        yield app.set(drivername="postgresql", database=name).render_as_string(hide_password=False)
    finally:
        logging.disable(logging.NOTSET)
        if before is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = before
        with psycopg.connect(admin, autocommit=True) as a:
            a.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def migration_files() -> dict:
    """The migration chain as the files state it: how many revisions, and the head(s)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "core" / "db" / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    return {"revisions": sum(1 for _ in script.walk_revisions()), "heads": sorted(script.get_heads())}
