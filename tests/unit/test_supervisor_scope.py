"""Regulator portal — the access gate must never open for a non-regulator, and only FILED statuses are visible.

The cross-entity scope (a regulator sees only its supervised_org set) is enforced in SQL and covered by the
integration smoke test; here we lock the two pure invariants that must never regress:
  1. require_supervisor 403s any org whose type is not 'regulator'.
  2. Only submitted-or-beyond statuses count as visible to a regulator (drafts/rejected never shown).
"""
import pytest
from fastapi import HTTPException

from api.routers.supervisor import FILED, require_supervisor


def _ctx(org_type: str) -> dict:
    return {"org": {"org_id": "o1", "type": org_type, "name": "X"}, "user": {"id": "u1"}, "permissions": []}


def test_regulator_passes_the_gate():
    ctx = _ctx("regulator"); ctx["permissions"] = ["supervisor.population.view"]
    assert require_supervisor(ctx) is ctx


def test_regulator_without_supervisory_permission_is_forbidden():
    with pytest.raises(HTTPException) as e:
        require_supervisor(_ctx("regulator"))      # right org type, no supervisory role
    assert e.value.status_code == 403 and "supervisor.population.view" in str(e.value.detail)


@pytest.mark.parametrize("t", ["bank", "insurer", "asset_manager", "reit", "manufacturer", "", None])
def test_non_regulator_is_forbidden(t):
    with pytest.raises(HTTPException) as e:
        require_supervisor(_ctx(t))
    assert e.value.status_code == 403


def test_only_filed_statuses_are_visible():
    # drafts / rejected must never be in the visible set a regulator can see
    assert "draft" not in FILED and "rejected" not in FILED
    assert {"submitted", "accepted", "approved", "attested", "released"} == set(FILED)
