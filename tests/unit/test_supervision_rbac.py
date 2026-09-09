"""The supervisor permission family in the migration must cover every code the profile registry's roles use."""
import importlib.util
from pathlib import Path

from services.governance.tenant_provisioning import (
    DEFAULT_ROLE_PERMS,
    VALID_ORG_TYPES,
    role_templates_for,
)
from services.supervision.profiles import all_permission_codes

MIG = Path(__file__).resolve().parents[2] / "core" / "db" / "migrations" / "versions" / "sup_perms_20260907.py"


def _migration_codes() -> set[str]:
    """Every supervisor permission any migration declares: the original batch (NEW) and later single additions (PERM)."""
    codes: set[str] = set()
    for path in sorted(MIG.parent.glob("sup_*.py")):
        spec = importlib.util.spec_from_file_location(path.stem, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        codes |= {c for c, _ in getattr(m, "NEW", [])}
        if getattr(m, "PERM", None):
            codes.add(m.PERM[0])
    return codes


def test_every_supervisor_code_in_registry_is_migrated():
    sup = {c for c in all_permission_codes() if c.startswith("supervisor.")}
    assert sup and sup <= _migration_codes()


def test_regulator_role_templates_come_from_the_registry():
    assert "regulator" in VALID_ORG_TYPES
    reg = role_templates_for("regulator")
    assert {"supervisor", "risk_analyst", "data_steward", "inspector", "policy", "head", "admin"} <= set(reg)
    assert all("supervisor.population.view" in p for p in reg.values())
    assert role_templates_for("bank") is DEFAULT_ROLE_PERMS


def test_every_role_declares_a_scope_and_case_roles_are_narrow():
    from services.supervision.assignments import ASSIGNED, POPULATION, effective_scope, role_scope
    from services.supervision.profiles import role_templates
    for name, r in role_templates().items():
        assert r.get("scope") in (ASSIGNED, POPULATION), name
    # people who work a case list see only their assignments; horizontal roles see the population
    assert role_scope("supervisor") == ASSIGNED and role_scope("inspector") == ASSIGNED
    assert role_scope("risk_analyst") == POPULATION and role_scope("head") == POPULATION
    # widest role wins; no supervisory role at all is the narrow scope; unknown custom roles are narrow
    assert effective_scope(["supervisor", "risk_analyst"]) == POPULATION
    assert effective_scope(["supervisor"]) == ASSIGNED
    assert effective_scope([]) == ASSIGNED and effective_scope(["custom_role"]) == ASSIGNED


def test_assignment_managers_hold_the_permission():
    from services.supervision.profiles import role_templates
    assert "supervisor.assignments.manage" in role_templates()["head"]["permissions"]
    assert "supervisor.assignments.manage" in role_templates()["admin"]["permissions"]


def test_scope_managers_hold_the_permission_and_it_is_migrated():
    from services.supervision.profiles import role_templates
    assert "supervisor.scope.manage" in role_templates()["head"]["permissions"]
    assert "supervisor.scope.manage" in _migration_codes()


def test_scope_respects_the_profile():
    from services.supervision.profiles import resolve
    from services.supervision.scope import profile_types
    assert profile_types(resolve("banking_supervisor")) == ["bank"]
    assert set(profile_types(resolve("integrated_supervisor"))) >= {"bank", "insurer", "asset_manager", "reit"}
