"""Guards (error log E5): the environment has what pyproject.toml declares, and the security headers are served.

A package the app imports but the declared list lacked once switched off the security headers and metrics silently,
and a second, stale requirements file drifted from the first. pyproject.toml is now the one list; this checks every
dependency CI installs (core + extras all, dev) is installed at a version that satisfies it."""
from __future__ import annotations

from importlib import metadata
from pathlib import Path

import pytest
import tomllib
from packaging.requirements import Requirement

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _declared() -> list[Requirement]:
    proj = tomllib.loads(PYPROJECT.read_text())["project"]
    extras = proj["optional-dependencies"]
    names = ["api", "ingest", "train", "otel", "dev"]          # what "all,dev" expands to (CI's install)
    reqs = [Requirement(r) for r in proj["dependencies"]]
    for e in names:
        reqs += [Requirement(r) for r in extras[e] if not r.startswith("climate-platform")]
    seen, out = set(), []
    for r in reqs:
        if r.name.lower() not in seen:
            seen.add(r.name.lower())
            out.append(r)
    return out


@pytest.mark.parametrize("req", _declared(), ids=lambda r: r.name)
def test_declared_dependency_installed(req):
    try:
        version = metadata.version(req.name)
    except metadata.PackageNotFoundError:
        pytest.fail(f"{req.name} is declared in pyproject.toml but not installed — run: pip install -e \".[all,dev]\"")
    assert req.specifier.contains(version, prereleases=True), f"{req.name} {version} does not satisfy {req.specifier}"


def test_security_headers_are_always_served():
    from fastapi.testclient import TestClient

    from api.main import app
    r = TestClient(app).get("/health")
    assert r.headers.get("X-Content-Type-Options") == "nosniff" and r.headers.get("X-Frame-Options") == "DENY"
    assert "max-age" in (r.headers.get("Strict-Transport-Security") or "")
