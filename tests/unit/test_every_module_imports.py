"""Guard (error log E3): every application module imports cleanly.

A module overwritten, half-renamed or left with a broken import fails here at once — not later, when a rarely used
endpoint is first called. Covers api/, services/, ml/ and core/ (scripts are run by hand and excluded)."""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ("api", "services", "ml", "core")
SKIP = ("core.db.migrations",)          # alembic revision files are loaded by alembic, not imported


def _modules() -> list[str]:
    out = []
    for pkg in PACKAGES:
        for m in pkgutil.walk_packages([str(ROOT / pkg)], prefix=f"{pkg}."):
            if not m.name.startswith(SKIP):
                out.append(m.name)
    return sorted(out)


@pytest.mark.parametrize("name", _modules())
def test_module_imports(name):
    importlib.import_module(name)
