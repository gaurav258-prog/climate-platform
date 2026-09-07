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
    spec = importlib.util.spec_from_file_location("sup_perms", MIG); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return {c for c, _ in m.NEW}


def test_every_supervisor_code_in_registry_is_migrated():
    sup = {c for c in all_permission_codes() if c.startswith("supervisor.")}
    assert sup and sup <= _migration_codes()


def test_regulator_role_templates_come_from_the_registry():
    assert "regulator" in VALID_ORG_TYPES
    reg = role_templates_for("regulator")
    assert {"supervisor", "risk_analyst", "data_steward", "inspector", "policy", "head", "admin"} <= set(reg)
    assert all("supervisor.population.view" in p for p in reg.values())
    assert role_templates_for("bank") is DEFAULT_ROLE_PERMS
