"""The four generated project documents match the code: docs/BACKEND_SCHEMA.md, docs/TECHNICAL_REQUIREMENTS.md,
docs/APP_FLOW.md and docs/DESIGN_BRIEF.md (scripts/project_docs/).

    venv/bin/python -m scripts.build_project_docs --check     (the gate step: exit 1 and a diff when one differs)
    venv/bin/python -m scripts.build_project_docs --write     (rewrite them from the code)

The schema is read from a scratch database the migration files build to head (about a minute), never from the
development database. `--database URL` reads an existing database instead, for a quick look while editing; a document
written that way describes that database, and the gate will say so if it differs from the migrations.
"""
from __future__ import annotations

import argparse
import difflib
import sys

from scripts.project_docs import catalogue, design, flow, schema, stack
from scripts.project_docs.source import REGENERATE, ROOT

DOCS = ("BACKEND_SCHEMA.md", "TECHNICAL_REQUIREMENTS.md", "APP_FLOW.md", "DESIGN_BRIEF.md")


def build(database: str | None = None) -> dict[str, str]:
    import psycopg

    migrations = catalogue.migration_files()
    if database:
        with psycopg.connect(database) as conn:
            cat = catalogue.read_catalogue(conn)
    else:
        with catalogue.head_database() as url, psycopg.connect(url) as conn:
            cat = catalogue.read_catalogue(conn)
    # the API is imported only after the scratch build has restored DATABASE_URL
    return {"BACKEND_SCHEMA.md": schema.render(cat, migrations),
            "TECHNICAL_REQUIREMENTS.md": stack.render(migrations),
            "APP_FLOW.md": flow.render(),
            "DESIGN_BRIEF.md": design.render()}


def compare(built: dict[str, str]) -> list[str]:
    """The documents whose file differs from what was built, each with the start of its diff."""
    out = []
    for name, text in built.items():
        path = ROOT / "docs" / name
        have = path.read_text(encoding="utf-8") if path.exists() else ""
        if have != text:
            diff = list(difflib.unified_diff(have.splitlines(), text.splitlines(), f"docs/{name} (file)",
                                             f"docs/{name} (from the code)", lineterm="", n=1))
            out.append("\n".join(diff[:40]) + (f"\n  … {len(diff) - 40} more diff lines" if len(diff) > 40 else ""))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="compare the documents with the code (default)")
    mode.add_argument("--write", action="store_true", help="rewrite the documents from the code")
    ap.add_argument("--database", help="read the schema from this database instead of a scratch build")
    args = ap.parse_args(argv)
    built = build(args.database)
    if args.write:
        for name, text in built.items():
            (ROOT / "docs" / name).write_text(text, encoding="utf-8")
        print("wrote " + ", ".join(f"docs/{n}" for n in built))
        return 0
    stale = compare(built)
    if stale:
        print("project documents differ from the code — regenerate them with\n  " + REGENERATE + "\nand commit the "
              "result:\n\n" + "\n\n".join(stale))
        return 1
    print("project documents match the code — " + ", ".join(DOCS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
