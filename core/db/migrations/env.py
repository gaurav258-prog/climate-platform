import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

load_dotenv()

# Import the regulatory (bank-vertical) models so their tables register on the
# shared Base.metadata — without this import Alembic cannot see them.
import core.db.models_regulatory_complete  # noqa: F401
from core.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# Override URL from environment
database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _path(revision: str) -> str:
    from alembic.script import ScriptDirectory
    return ScriptDirectory.from_config(config).get_revision(revision).path


def _record_applied(ctx, step, heads, run_args) -> None:
    """Keep the fingerprints of each migration FILE as it was applied (E100; core.db.migration_fingerprint, E172): a file
    edited after it ran against this database is then caught by scripts/check_applied_migrations.py (in the gate)
    instead of leaving the schema silently unlike the file — unless the edit is confined to its REFUSAL_PROBE. Kept
    outside the public schema, so the schema checks never see it."""
    conn = ctx.connection
    conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS migration_meta")
    conn.exec_driver_sql("""CREATE TABLE IF NOT EXISTS migration_meta.applied_file (
        revision TEXT PRIMARY KEY, sha256 TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    conn.exec_driver_sql("ALTER TABLE migration_meta.applied_file ADD COLUMN IF NOT EXISTS schema_sha256 TEXT")
    if step.is_upgrade:
        from core.db.migration_fingerprint import file_sha, schema_sha
        rev = step.up_revision_id
        conn.exec_driver_sql("""INSERT INTO migration_meta.applied_file (revision, sha256, schema_sha256)
                                VALUES (%(r)s, %(s)s, %(m)s)
                                ON CONFLICT (revision) DO UPDATE SET sha256 = EXCLUDED.sha256,
                                    schema_sha256 = EXCLUDED.schema_sha256, applied_at = now()""",
                             {"r": rev, "s": file_sha(_path(rev)), "m": schema_sha(_path(rev))})
    else:
        conn.exec_driver_sql("DELETE FROM migration_meta.applied_file WHERE revision = %(r)s", {"r": step.up_revision_id})


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, on_version_apply=_record_applied)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
