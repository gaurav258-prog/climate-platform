"""Fingerprints of a migration file (E100, E172).

  file_sha    the whole file, as it was applied
  schema_sha  the file without its REFUSAL_PROBE — the probe is a fixture the round-trip check plants to prove a
              downgrade refuses; it never runs on upgrade or downgrade, so editing it leaves the schema as it was —
              nor the module constants only the probe reads (its organisation's id, its run's id: part of the fixture,
              E314). Everything else (upgrade, downgrade, their helpers and constants) is in this fingerprint.
"""
from __future__ import annotations

import ast
import hashlib


def file_sha(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _assigned(n: ast.stmt) -> set[str]:
    """The names a module-level assignment binds (none for any other statement, or a non-name target)."""
    if not isinstance(n, (ast.Assign, ast.AnnAssign)):
        return set()
    targets = n.targets if isinstance(n, ast.Assign) else [n.target]
    return {t.id for t in targets if isinstance(t, ast.Name)} if all(isinstance(t, ast.Name) for t in targets) else set()


def _read(nodes) -> set[str]:
    return {x.id for n in nodes for x in ast.walk(n) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load)}


def schema_sha(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    probe = [n for n in tree.body if "REFUSAL_PROBE" in _assigned(n)]
    rest = [n for n in tree.body if n not in probe]
    fixture = set()                   # constants only the probe reads: bound here, read by the probe, read nowhere else
    for n in rest:
        names = _assigned(n)
        if names and names <= _read(probe) and not names & _read([m for m in rest if m is not n]):
            fixture.add(id(n))
    tree.body = [n for n in rest if id(n) not in fixture]
    return hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest()
