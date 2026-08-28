"""CI guard for the Alembic migration graph — fails the build on a broken chain.

Change-control safety net so the multiple-heads problem (which forced the app onto create_all)
can never silently return. Static analysis only — no database needed, so it runs in any CI stage.

Checks:
  1. Exactly ONE head (no divergent branches left un-merged).
  2. Every `down_revision` points at a revision that actually exists (no dangling links).
  3. No duplicate revision ids.

Usage:  python -m scripts.check_migrations      (exit 0 = ok, non-zero = fail)
"""
from __future__ import annotations

import glob
import os
import re
import sys

VERSIONS = os.path.join(os.path.dirname(__file__), "..", "core", "db", "migrations", "versions")


def _idents(expr: str) -> list[str]:
    """Pull revision ids out of a `down_revision = ...` RHS (handles None, str, or tuple)."""
    return re.findall(r"""["']([A-Za-z0-9_]+)["']""", expr)


def main() -> int:
    revs: dict[str, str] = {}
    downs: dict[str, list[str]] = {}
    dupes: list[str] = []
    for path in glob.glob(os.path.join(VERSIONS, "*.py")):
        text = open(path).read()
        # handle both `revision = "x"` and the annotated `revision: str = "x"`
        rm = re.search(r"^revision\s*(?::[^=\n]+)?=\s*['\"]([^'\"]+)['\"]", text, re.M)
        dm = re.search(r"^down_revision\s*(?::[^=\n]+)?=\s*(.+)$", text, re.M)
        if not rm:
            continue
        rid = rm.group(1)
        if rid in revs:
            dupes.append(rid)
        revs[rid] = os.path.basename(path)
        downs[rid] = _idents(dm.group(1)) if dm else []

    errors: list[str] = []
    if dupes:
        errors.append(f"duplicate revision id(s): {sorted(set(dupes))}")

    # dangling down_revisions
    for rid, parents in downs.items():
        for p in parents:
            if p not in revs:
                errors.append(f"{revs[rid]}: down_revision '{p}' does not exist")

    # heads = revisions that no other revision points back to
    referenced = {p for parents in downs.values() for p in parents}
    heads = [rid for rid in revs if rid not in referenced]
    if len(heads) != 1:
        errors.append(f"expected exactly 1 head, found {len(heads)}: {sorted(heads)} — run `alembic merge heads`")

    if errors:
        print("MIGRATION CHECK FAILED:")
        for e in errors:
            print("  -", e)
        return 1
    print(f"migration check OK — {len(revs)} revisions, single head: {heads[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
