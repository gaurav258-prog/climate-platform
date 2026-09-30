"""The year-end close and restatement, end to end through the HTTP API, in one rolled-back transaction (Terra Foods):

  close        the analyst asks to close FY2025 for an undertaking; the analyst cannot approve it (four eyes); the
               approver does → the period is closed and listed with both names
  refused      a provided value for the closed period without a reason; a second close; a close while a value for the
               period still awaits attestation
  restatement  a provided value with its reason; a site's carrying amount restated with its reason → lands only when
               the approver approves, as a new statement beside the first (the live value is the restated one)
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration
TERRA = "55555555-5555-4555-8555-555555555555"


def _users(api):
    return _login(api, "analyst@terra.demo", "Demo!analyst1"), _login(api, "approver@terra.demo", "Demo!approve1")


def _approve(api, checker, rid, reason="reviewed against the ledger"):
    r = api.post(f"/v1/approvals/{rid}/decide", headers=checker, json={"decision": "approved", "reason": reason})
    assert r.status_code == 200, r.text
    return r.json()


def test_the_year_end_close_and_the_restatement_of_a_closed_period(api):
    maker, checker = _users(api)
    s = api.s
    site, ent = s.execute(text("""SELECT site_id::text, entity_id::text FROM sc_company_sites WHERE org_id = CAST(:o AS uuid)
                                  AND entity_id IS NOT NULL ORDER BY name LIMIT 1"""), {"o": TERRA}).one()
    s.execute(text("""INSERT INTO site_period_values (org_id, site_id, reporting_entity_id, period_end, measure, amount,
                                                      currency, amount_eur, source)
                      VALUES (CAST(:o AS uuid), CAST(:s AS uuid), CAST(:e AS uuid), '2025-12-31', 'carrying_amount',
                              4000000, 'EUR', 4000000, 'client')"""), {"o": TERRA, "s": site, "e": ent})

    # a value still awaiting its second person keeps the period open
    p = api.post("/v1/provided", headers=maker, json={"framework": "csrd_e1", "datapoint_key": "e1_ghg", "value_num": 125000,
                                                      "reporting_period_end": "2025-12-31"})
    assert p.status_code == 201, p.text
    blocked = api.post("/v1/periods/close", headers=maker, json={"period_end": "2025-12-31"})
    assert blocked.status_code == 409 and "await attestation" in blocked.text
    _approve(api, checker, p.json()["approval_request_id"])

    # the organisation's own period and the undertaking's period close separately, each with four eyes
    for body in ({"period_end": "2025-12-31"}, {"period_end": "2025-12-31", "entity_id": ent}):
        r = api.post("/v1/periods/close", headers=maker, json={**body, "note": "FY2025 books closed"})
        assert r.status_code == 202, r.text
        rid = r.json()["approval_request_id"]
        own = api.post(f"/v1/approvals/{rid}/decide", headers=maker, json={"decision": "approved", "reason": "mine"})
        assert own.status_code in (403, 422)                          # the maker never approves their own close
        _approve(api, checker, rid)
    closes = api.get("/v1/periods", headers=maker).json()["closes"]
    mine = [c for c in closes if c["period_end"] == "2025-12-31"]
    assert len(mine) == 2 and all(c["requested_by"] and c["approved_by"] and c["requested_by"] != c["approved_by"] for c in mine)
    again = api.post("/v1/periods/close", headers=maker, json={"period_end": "2025-12-31"})
    assert again.status_code == 409 and "already closed" in again.text

    # a closed period's value is a restatement: refused without its reason, accepted with it (then attested)
    body = {"framework": "csrd_e1", "datapoint_key": "e1_ghg", "value_num": 131000, "reporting_period_end": "2025-12-31"}
    assert api.post("/v1/provided", headers=maker, json=body).status_code == 400
    r = api.post("/v1/provided", headers=maker, json={**body, "restatement_reason": "Scope 3 cat. 1 recalculated with supplier data"})
    assert r.status_code == 201, r.text
    _approve(api, checker, r.json()["approval_request_id"])

    # the site's carrying amount restated: nothing lands until the second person approves; then a new statement
    r = api.post("/v1/periods/restatements/site-value", headers=maker, json={
        "site_id": site, "period_end": "2025-12-31", "measure": "carrying_amount", "amount": 3600000, "currency": "EUR",
        "reason": "impairment of the cold store identified in the audit"})
    assert r.status_code == 202, r.text
    def live() -> float:
        return float(s.execute(text("""SELECT amount_eur FROM v_site_period_values_live WHERE site_id = CAST(:s AS uuid)
                                       AND period_end = '2025-12-31' AND measure = 'carrying_amount'"""), {"s": site}).scalar())
    assert live() == 4000000
    _approve(api, checker, r.json()["approval_request_id"])
    assert live() == 3600000
    hist = s.execute(text("""SELECT amount_eur, restatement_reason FROM site_period_values WHERE site_id = CAST(:s AS uuid)
                             AND period_end = '2025-12-31' AND measure = 'carrying_amount' ORDER BY seq"""), {"s": site}).all()
    assert [(float(a), w) for a, w in hist] == [(4000000, None), (3600000, "impairment of the cold store identified in the audit")]

    # an open period is not restated — its value is simply sent
    r = api.post("/v1/periods/restatements/site-value", headers=maker, json={
        "site_id": site, "period_end": "2024-12-31", "measure": "carrying_amount", "amount": 1, "currency": "EUR",
        "reason": "this period was never closed"})
    assert r.status_code == 409 and "the period is open" in r.text
