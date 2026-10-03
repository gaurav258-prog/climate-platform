"""E143: every LEI the platform stores passes ONE check (services.reference.gleif.verified_lei) — the organisation's
(admin settings), a new tenant's, the filing profile's and a fund's: ISO 17442 check digits, then a record in GLEIF;
GLEIF unreachable is refused, never stored unverified. GLEIF is stubbed: no network."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from services.reference import gleif
from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration
REAL = "5493001KJTIIGC8Y1R12"            # valid check digits


@pytest.fixture
def registry(monkeypatch):
    state = {"known": {REAL}, "down": False}

    def fetch(lei):
        if state["down"]:
            raise gleif.GleifError("GLEIF 503")
        return gleif.GleifRecord(lei=lei, name="Registered Name") if lei in state["known"] else None
    monkeypatch.setattr(gleif, "fetch_lei", fetch)
    return state


def test_verified_lei_refuses_what_is_not_a_registered_lei(registry):
    for bad in ("", "NOT-A-LEI", "LEI0000000000000GOLD", "5493001KJTIIGC8Y1R13"):     # format / check digits: no lookup
        with pytest.raises(gleif.LeiError, match="not a valid LEI"):
            gleif.verified_lei(bad)
    with pytest.raises(gleif.LeiError, match="not in GLEIF"):
        gleif.verified_lei("5493000TESTNOTREG033")
    assert gleif.verified_lei(REAL.lower()).lei == REAL
    registry["down"] = True
    with pytest.raises(gleif.LeiError, match="could not be reached"):
        gleif.verified_lei(REAL)


def test_admin_settings_store_only_a_verified_lei(api, registry):
    admin = _login(api, "admin@nordkap.demo", "Demo!admin1")
    org_id = api.get("/v1/auth/me", headers=admin).json()["org"]["org_id"]
    before = api.s.execute(text("SELECT lei FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": org_id}).scalar()
    for bad, why in (("LEI0000000000000GOLD", "not a valid LEI"), ("5493000TESTNOTREG033", "not in GLEIF")):
        r = api.patch("/v1/admin/organization", headers=admin, json={"lei": bad})
        assert r.status_code == 422 and why in r.text, r.text
    registry["down"] = True
    assert api.patch("/v1/admin/organization", headers=admin, json={"lei": REAL}).status_code == 422
    assert api.s.execute(text("SELECT lei FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": org_id}).scalar() == before
    registry["down"] = False
    assert api.patch("/v1/admin/organization", headers=admin, json={"lei": REAL.lower()}).status_code == 200
    assert api.s.execute(text("SELECT lei FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": org_id}).scalar() == REAL
    registry["down"] = True                  # unchanged (the form re-sends it with another field): not re-verified
    r = api.patch("/v1/admin/organization", headers=admin, json={"lei": REAL, "filing_contact_email": "c@nordkap.demo"})
    assert r.status_code == 200 and "lei" not in r.json()["changes"]
    assert api.patch("/v1/admin/organization", headers=admin, json={"lei": ""}).status_code == 200      # cleared
    assert api.s.execute(text("SELECT lei FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": org_id}).scalar() is None


def test_a_new_tenant_and_a_fund_take_the_same_check(api, registry):
    from services.governance.tenant_provisioning import TenantError, create_tenant
    with pytest.raises(TenantError, match="not in GLEIF"):
        create_tenant(api.s, actor_user_id=None, name="LEI check tenant (test)", org_type="bank", country="DE",
                      lei="5493000TESTNOTREG033")
    analyst = _login(api, "analyst@nordkap.demo", "Demo!analyst1")
    fund = api.get("/v1/funds", headers=analyst).json()["funds"][0]["fund_id"]
    r = api.put(f"/v1/funds/{fund}/lei", headers=analyst, json={"lei": "LEI0000000000000GOLD"})
    assert r.status_code == 422 and "not a valid LEI" in r.text
