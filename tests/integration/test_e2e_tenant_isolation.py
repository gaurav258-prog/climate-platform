"""End to end, through the HTTP API: no record crosses a tenant boundary, and anonymous access is read-only (E24).

  * a record addressed by id is served only to its own organisation — to an anonymous caller only the sector's public
    demo records; another tenant's id answers 404 (the same as an id that does not exist)
  * anonymous callers cannot change anything; a signed-in preparer can
  * refusals are real HTTP errors with a message, never a 200 carrying an 'error' field
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.integration.conftest import login

pytestmark = pytest.mark.integration
BANK_DEMO, AM_DEMO = "11111111-1111-4111-8111-111111111111", "44444444-4444-4444-8444-444444444444"


def _one(s, sql, **p):
    return s.execute(text(sql), p).scalar()


def test_records_are_served_only_to_their_own_organisation(api):
    s = api.s
    other_bank = _one(s, "SELECT entity_id::text FROM portfolio_entities WHERE vertical='banking' AND org_id <> CAST(:o AS uuid) LIMIT 1", o=BANK_DEMO)
    own_bank = _one(s, "SELECT entity_id::text FROM portfolio_entities WHERE vertical='banking' AND org_id = CAST(:o AS uuid) LIMIT 1", o=BANK_DEMO)
    other_plot = _one(s, "SELECT plot_id::text FROM sc_sourcing_plots WHERE org_id <> '55555555-5555-4555-8555-555555555555' LIMIT 1")
    other_policy = _one(s, "SELECT entity_id::text FROM portfolio_entities WHERE vertical='insurance' AND org_id <> '22222222-2222-4222-8222-222222222222' LIMIT 1")
    for path in (f"/v1/bank/asset/{other_bank}", f"/v1/supply/plot/{other_plot}", f"/v1/insurance/policy/{other_policy}",
                 "/v1/bank/asset/not-an-id"):
        r = api.get(path)                                            # anonymous
        assert r.status_code == 404 and r.json()["error"]["message"].endswith("not found."), (path, r.status_code)
    assert api.get(f"/v1/bank/asset/{own_bank}").status_code == 200        # the public demo record
    # a signed-in user of another organisation sees the same 404 for the demo bank's record
    terra = login(api, "admin@terra.demo", "Demo!admin1")
    assert api.get(f"/v1/bank/asset/{own_bank}", headers=terra).status_code == 404
    meridian = login(api, "admin@meridian.demo", "Demo!admin1")
    assert api.get(f"/v1/bank/asset/{own_bank}", headers=meridian).status_code == 200


def test_anonymous_access_is_read_only_and_refusals_are_http_errors(api):
    s = api.s
    fund = _one(s, "SELECT fund_id::text FROM funds WHERE org_id = CAST(:o AS uuid) LIMIT 1", o=AM_DEMO)
    r = api.put(f"/v1/funds/{fund}/voluntary-pai", json={"indicator_keys": ["t2_6_1", "t3_5"]})
    assert r.status_code in (401, 403)                                # anonymous: no writes
    mgr = login(api, "admin@nordkap.demo", "Demo!admin1")
    bad = api.put(f"/v1/funds/{fund}/voluntary-pai", headers=mgr, json={"indicator_keys": ["t2_6_1", "water_consumption_m3_per_meur"]})
    assert bad.status_code == 422 and "Not an adoptable indicator" in bad.json()["error"]["message"]
    ok = api.put(f"/v1/funds/{fund}/voluntary-pai", headers=mgr, json={"indicator_keys": ["t2_6_1", "t3_5"]})
    assert ok.status_code == 200 and ok.json()["adoption_compliant"] is True
    other_fund = _one(s, "SELECT fund_id::text FROM funds WHERE org_id <> CAST(:o AS uuid) LIMIT 1", o=AM_DEMO)
    if other_fund:
        assert api.get(f"/v1/funds/{other_fund}", headers=mgr).status_code == 404    # never 'forbidden' (existence hidden)


def test_fund_indicator_values_are_stored_or_refused_never_dropped(api):
    """SFDR additional indicators end to end: adopt by official key → upload holdings carrying values → each value is
    stored (right kind for its metric) or refused and reported back to the uploader (E24: never silently dropped)."""
    s = api.s
    mgr = login(api, "admin@nordkap.demo", "Demo!admin1")
    fund = _one(s, "SELECT fund_id::text FROM funds WHERE org_id = CAST(:o AS uuid) LIMIT 1", o=AM_DEMO)
    isin = _one(s, """SELECT s.isin FROM fund_positions p JOIN securities s ON s.security_id = p.security_id
                      WHERE p.fund_id = CAST(:f AS uuid) AND s.isin IS NOT NULL LIMIT 1""", f=fund)
    assert api.put(f"/v1/funds/{fund}/voluntary-pai", headers=mgr,
                   json={"indicator_keys": ["t2_6_1", "t3_5"]}).status_code == 200
    body = {"holdings": [{"isin": isin, "market_value_eur": 1_000_000, "reporting_year": 2025,
                          "voluntary_pai": {"t3_5": True, "t2_6_1": 0.42, "t2_4": 3.0, "no_such_indicator": 1}}]}
    r = api.post(f"/v1/funds/{fund}/holdings", headers=mgr, json=body)
    assert r.status_code == 200, r.text
    refused = {(x["key"], x["reason"]) for x in r.json()["voluntary_rejected"]}
    assert refused == {("t2_4", "needs yes/no (true/false)"), ("no_such_indicator", "not an adoptable indicator")}
    assert all(x["isin"] == isin for x in r.json()["voluntary_rejected"])
    stored = dict(s.execute(text("""SELECT v.indicator_key, COALESCE(v.value_num::text, v.value_bool::text)
                                    FROM issuer_voluntary_pai v JOIN securities sc ON sc.issuer_id = v.issuer_id
                                    WHERE sc.isin = :i AND v.org_id = CAST(:o AS uuid) AND v.reporting_year = 2025"""),
                            {"i": isin, "o": AM_DEMO}).all())
    assert stored.get("t3_5") == "true" and float(stored["t2_6_1"]) == 0.42
    assert "t2_4" not in stored and "no_such_indicator" not in stored
    assert api.post(f"/v1/funds/{fund}/holdings", json=body).status_code in (401, 403)    # anonymous: no writes
