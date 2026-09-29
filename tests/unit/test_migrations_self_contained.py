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
