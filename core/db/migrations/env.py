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


def _file_sha(revision: str) -> str:
    import hashlib

    from alembic.script import ScriptDirectory
    path = ScriptDirectory.from_config(config).get_revision(revision).path
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _record_applied(ctx, step, heads, run_args) -> None:
    """Keep the hash of each migration FILE as it was applied (E100): a file edited after it ran against this database
    is then caught by scripts/check_applied_migrations.py (in the gate) instead of leaving the schema silently unlike
    the file. Kept outside the public schema, so the schema checks never see it."""
    conn = ctx.connection
    conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS migration_meta")
    conn.exec_driver_sql("""CREATE TABLE IF NOT EXISTS migration_meta.applied_file (
        revision TEXT PRIMARY KEY, sha256 TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    if step.is_upgrade:
        rev = step.up_revision_id
        conn.exec_driver_sql("""INSERT INTO migration_meta.applied_file (revision, sha256) VALUES (%(r)s, %(s)s)
                                ON CONFLICT (revision) DO UPDATE SET sha256 = EXCLUDED.sha256, applied_at = now()""",
                             {"r": rev, "s": _file_sha(rev)})
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
