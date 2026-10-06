"""Fingerprints of a migration file (E100, E172).

  file_sha    the whole file, as it was applied
  schema_sha  the file without its REFUSAL_PROBE — the probe is a fixture the round-trip check plants to prove a
              downgrade refuses; it never runs on upgrade or downgrade, so editing it leaves the schema as it was.
              Everything else (upgrade, downgrade, their helpers and constants) is in this fingerprint.
"""
from __future__ import annotations

import ast
import hashlib


def file_sha(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def schema_sha(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    tree.body = [n for n in tree.body if not (isinstance(n, (ast.Assign, ast.AnnAssign)) and any(
        isinstance(t, ast.Name) and t.id == "REFUSAL_PROBE" for t in (n.targets if isinstance(n, ast.Assign) else [n.target])))]
    return hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest()
