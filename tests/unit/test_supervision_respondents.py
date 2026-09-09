"""Respondents: a supervised entity not on Tellumen gets exactly the portal role, nothing else."""
from services.governance.tenant_provisioning import (
    DEFAULT_ROLE_PERMS,
    RESPONDENT_ROLE_PERMS,
    role_templates_for,
)


def test_respondent_role_is_minimal_and_only_for_respondents():
    r = role_templates_for("bank", plan="respondent")
    assert set(r) == {"respondent"} and "respondent.portal" in r["respondent"]
    assert not ({"pricing.view", "approvals.decide", "portal.use"} & set(r["respondent"]))
    assert role_templates_for("bank") is DEFAULT_ROLE_PERMS and RESPONDENT_ROLE_PERMS["respondent"]


def test_respondent_role_is_migrated():
    from pathlib import Path
    mig = Path(__file__).resolve().parents[2] / "core" / "db" / "migrations" / "versions" / "sup_respondent_20260909.py"
    assert "respondent.portal" in mig.read_text()
