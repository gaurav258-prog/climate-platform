"""E146: an organisation withdraws the data it stated about an issuer — every org-scoped row goes (kept in the audit
record with the reason); the shared reference and another organisation's data stay; a reason is required; nothing of
its own left is a 404, as is an organisation that holds none."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration


def test_an_organisation_withdraws_only_its_own_issuer_data(api):
    s = api.s
    nk = _login(api, "analyst@nordkap.demo", "Demo!analyst1")
    org = api.get("/v1/auth/me", headers=nk).json()["org"]["org_id"]
    other = s.execute(text("SELECT org_id::text FROM organizations WHERE name = 'Meridian Bank (demo)'")).scalar()
    iid = s.execute(text("""INSERT INTO issuers (lei, name, issuer_type, country) VALUES ('TESTWITHDRAW00000001', 'Withdraw test issuer',
                            'corporate', 'DE') RETURNING issuer_id::text""")).scalar()
    for o, src in ((org, "client"), (org, "estimated"), (other, "client"), (None, "disclosed")):
        s.execute(text("""INSERT INTO issuer_emissions (issuer_id, org_id, reporting_year, scope1_tco2e, source)
                          VALUES (CAST(:i AS uuid), CAST(:o AS uuid), 2024, 100, :s)"""), {"i": iid, "o": o, "s": src})
    s.execute(text("""INSERT INTO issuer_esg_metrics (issuer_id, org_id, reporting_year, board_female_pct, source)
                      VALUES (CAST(:i AS uuid), CAST(:o AS uuid), 2024, 40, 'client')"""), {"i": iid, "o": org})

    from services.issuer_taxonomy import write_total
    write_total(s, iid, org, 2024, "turnover", {"aligned": 10.0, "fossil_gas": 0.0, "nuclear": 0.0})

    url = f"/v1/issuers/{iid}/client-data/withdraw"
    assert api.post(url, headers=nk, json={"reason": "wrong"}).status_code == 422                 # a reason, in words
    r = api.post(url, headers=nk, json={"reason": "uploaded for the wrong company"})
    assert r.status_code == 200, r.text
    assert r.json()["withdrawn"] == {"issuer_emissions": 2, "issuer_esg_metrics": 1, "issuer_taxonomy_kpi": 1}
    left = s.execute(text("""SELECT coalesce(org_id::text, 'reference') FROM issuer_emissions WHERE issuer_id = CAST(:i AS uuid)
                             ORDER BY 1"""), {"i": iid}).scalars().all()
    assert sorted(left) == sorted([other, "reference"])
    audit = s.execute(text("""SELECT detail FROM access_audit_log WHERE action = 'issuer.client_data_withdrawn'
                              AND target_id = :i"""), {"i": iid}).scalar()
    assert audit["reason"] == "uploaded for the wrong company" and len(audit["rows"]["issuer_emissions"]) == 2
    again = api.post(url, headers=nk, json={"reason": "uploaded for the wrong company"})
    assert again.status_code == 404 and "no data of its own" in again.text
    stellar = _login(api, "analyst@stellar.demo", "Demo!analyst1")
    assert api.post(url, headers=stellar, json={"reason": "not ours to withdraw"}).status_code == 404
    assert api.post("/v1/issuers/not-a-uuid/client-data/withdraw", headers=nk, json={"reason": "x" * 12}).status_code == 422
