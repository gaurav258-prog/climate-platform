"""A migration is self-contained: it never imports the application (error log E25).

A migration that reads live code (a vocabulary list, an ORM model, a sync helper) builds today's shape instead of its
own — so replaying history gives a different database than the one that was migrated, and its downgrade cannot know
what to restore. Every list, table definition and view a migration needs is written into the migration itself.
scripts/check_migration_roundtrip.py then proves every step undoes exactly.
"""
import pathlib
import re

VERSIONS = pathlib.Path(__file__).resolve().parents[2] / "core" / "db" / "migrations" / "versions"
_APP_IMPORT = re.compile(r"^\s*(from|import)\s+(core|services|ml|api|scripts|workers)\b", re.M)


def test_no_migration_imports_the_application():
    offenders = sorted(p.name for p in VERSIONS.glob("*.py") if _APP_IMPORT.search(p.read_text()))
    assert not offenders, f"migrations importing application code (freeze what they need into the file): {offenders}"


def test_every_revision_id_fits_the_version_column():
    """alembic_version.version_num is VARCHAR(32): a longer id migrates nothing and fails at the stamp (E69)."""
    ids = {p.name: re.search(r'^revision(?::[^=]*)?=\s*["\']([^"\']+)', p.read_text(), re.M) for p in VERSIONS.glob("*.py")}
    long = sorted(f"{n}: {m.group(1)}" for n, m in ids.items() if m and len(m.group(1)) > 32)
    assert not long, f"revision ids longer than 32 characters: {long}"
