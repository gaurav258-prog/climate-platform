"""E352 guard: a test of the case where no undertaking states its CSRD reporting role builds that case itself.

A demo organisation's roles are its governed statements and change by the product owner's decisions (2026-10-31: the
Meridian and Stellar groups' parents state the consolidated role for FY2025). csrd_reporting_role is append-only, so a test
on a demo organisation that asserts 'no one files this report yet' must move the organisation's reporting period to a year
with no role stated (tests.integration.filers.year_without_roles, inside its rolled-back transaction) — never rely on the
demo data having stated none.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

INTEGRATION = Path(__file__).resolve().parents[1] / "integration"
NO_ROLE_MARKERS = ("kri.filer.none", "disclose.esrs.scope.role_needed", "filers_to_state")
DEMO_MARKERS = ("BANK_ORG", "(demo)", ".demo\"", "IBERIA")


def _offenders() -> list[str]:
    out = []
    for f in sorted(INTEGRATION.glob("test_*.py")):
        src = f.read_text()
        if not any(m in src for m in NO_ROLE_MARKERS):
            continue
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                body = ast.get_source_segment(src, node) or ""
                if (any(m in body for m in NO_ROLE_MARKERS) and any(m in body for m in DEMO_MARKERS)
                        and "year_without_roles(" not in body):
                    out.append(f"{f.name}::{node.name}")
    return out


def test_no_role_cases_on_demo_organisations_build_their_year():
    assert _offenders() == [], ("these tests assert the no-role case on a demo organisation without building it "
                                f"(use tests.integration.filers.year_without_roles): {_offenders()}")


def test_the_guard_sees_a_test_that_relies_on_demo_data(tmp_path, monkeypatch):
    (tmp_path / "test_probe.py").write_text(
        'def test_probe(api):\n    r = api.get(f"/v1/reg-tasks/kri?org={BANK_ORG}")\n'
        '    assert r.json()["notice"]["code"] == "kri.filer.none"\n')
    monkeypatch.setattr(sys.modules[__name__], "INTEGRATION", tmp_path)
    assert _offenders() == ["test_probe.py::test_probe"]
