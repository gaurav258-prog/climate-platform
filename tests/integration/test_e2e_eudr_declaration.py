"""EUDR simplified declaration end to end (E115), through the HTTP API in one rolled-back transaction (Terra Foods; maker /
checker; a reporting entity of the test's own, so the organisation's demo status never decides what it sees — E81):

  who        blocked until the undertaking is micro or small, established in a low-risk country, and states that it places
             its own produce (Art. 2(15a)); a medium undertaking files due diligence statements instead
  what       Annex III: the products with their one-off estimated annual quantity; every plot with a geolocation (Art.
             2(28)) or its postal address (Art. 4a(5)) — a plot with neither blocks
  filing     prepared → four eyes → attested → submitted → declaration identifier → accepted; one live declaration
  update     after major changes: a new declaration superseding the accepted one, accepted only with the same identifier
             (IR 2024/3084 Art. 4a(3))
  withdraw   refused once grouped (Art. 4a(7)) — in the service and in the database
  rejected   by the authority, also after the identifier (Art. 8 sets no identifier limit for declarations)
  form       Annex III point by point, as printed in the captured spec
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration
TERRA = "55555555-5555-4555-8555-555555555555"
SQUARE = {"type": "Polygon", "coordinates": [[[-1.606123, 6.694123], [-1.604123, 6.694123], [-1.604123, 6.696123],
                                              [-1.606123, 6.696123], [-1.606123, 6.694123]]]}


def _entity(s) -> str:
    return s.execute(text("""INSERT INTO reporting_entities (entity_id, org_id, name) VALUES (gen_random_uuid(),
                             CAST(:o AS uuid), 'E115 cocoa farm') RETURNING entity_id::text"""), {"o": TERRA}).scalar()


def _plot(s, ent, *, polygon=False, decimals=None, postal=None, name="E115 plot") -> str:
    return s.execute(text("""
        INSERT INTO sc_sourcing_plots (org_id, plot_name, latitude, longitude, country, plot_geometry, plot_area_ha,
                                       coordinate_decimals, postal_address, entity_id, commodity_id)
        VALUES (CAST(:o AS uuid), :n, 6.695123, -1.605123, 'GH', CAST(:g AS jsonb), 2.0, :d, :pa, CAST(:e AS uuid),
                (SELECT commodity_id FROM sc_commodities WHERE name = 'Cocoa')) RETURNING plot_id::text"""),
        {"o": TERRA, "n": name, "g": json.dumps(SQUARE) if polygon else None, "d": decimals, "pa": postal, "e": ent}).scalar()


def _approve(api, checker, r):
    assert r.status_code == 202, r.text
    d = api.post(f"/v1/approvals/{r.json()['approval_request_id']}/decide", headers=checker, json={"decision": "approved", "reason": "ok"})
    assert d.status_code == 200, d.text


def _status(api, maker, checker, ent, size="small", own=True):
    _approve(api, checker, api.post("/v1/eudr/status", headers=maker, json={
        "effective_from": "2026-01-01", "size_class": size, "country": "GH", "address": "PO Box 12, Kumasi",
        "eori": "GH1234567", "entity_id": ent, "primary_own_produce": own}))


def _blocking(api, h, ent) -> set[str]:
    st = api.get(f"/v1/eudr/declaration?entity_id={ent}", headers=h).json()
    return {c["rule"].split(":")[0] for c in st["checks"] if not c["passed"] and c["severity"] == "blocking"}


def _file(api, maker, checker, fid):
    sr = api.post(f"/v1/filings/{fid}/submit-for-review", headers=maker)
    assert sr.status_code == 200, sr.text
    d = api.post(f"/v1/approvals/{sr.json()['approval_request_id']}/decide", headers=checker, json={"decision": "approved", "reason": "ok"})
    assert d.status_code == 200, d.text
    assert api.post(f"/v1/filings/{fid}/attest", headers=checker, json={"statement": "Signed for the farm."}).status_code == 200
    assert api.post(f"/v1/filings/{fid}/submit", headers=maker, json={"submission_ref": "EUDR-IS"}).status_code == 200


def _status_of(s, fid) -> str:
    return s.execute(text("SELECT status FROM regulatory_filing WHERE filing_id = CAST(:f AS uuid)"), {"f": fid}).scalar()


def test_a_simplified_declaration_is_made_filed_identified_and_updated(api):
    s = api.s
    maker, checker = _login(api, "analyst@terra.demo", "Demo!analyst1"), _login(api, "approver@terra.demo", "Demo!approve1")
    ent = _entity(s)

    # nothing in place: who, what and where all block
    assert {"annex_iii_1", "annex_iii_2", "annex_iii_3"} <= _blocking(api, maker, ent)

    # a medium undertaking is not a primary operator; nor one that does not state its own produce
    _status(api, maker, checker, ent, size="medium", own=None)
    assert {"filer", "own_produce"} <= _blocking(api, maker, ent)
    _status(api, maker, checker, ent, size="small", own=True)
    assert not {"filer", "own_produce", "filer_country"} & _blocking(api, maker, ent)

    # the products: a quantity is required; customs flow in kilograms
    bad = api.post("/v1/eudr/declaration/lines", headers=maker, json={"entity_id": ent, "hs_code": "180100",
                                                                      "description": "Cocoa beans", "customs_flow": True})
    assert bad.status_code == 422 and "estimated annual quantity" in bad.text
    milk = api.post("/v1/eudr/declaration/lines", headers=maker, json={"entity_id": ent, "hs_code": "0401", "description": "Milk",
                                                                       "customs_flow": False, "est_net_mass_kg": 10})
    assert milk.status_code == 422 and "not a relevant product" in milk.text
    ln = api.post("/v1/eudr/declaration/lines", headers=maker, json={"entity_id": ent, "hs_code": "180100",
                                                                     "description": "Cocoa beans, whole, raw", "customs_flow": True,
                                                                     "est_net_mass_kg": 12000, "trade_name": "Ashanti beans"})
    assert ln.status_code == 201, ln.text

    # where: geolocation per Art. 2(28), or the postal address (Art. 4a(5)); a plot with neither blocks
    _plot(s, ent, polygon=True, decimals=6, name="E115 surveyed")
    bare = _plot(s, ent, decimals=4, name="E115 bare")
    assert "location" in _blocking(api, maker, ent)
    s.execute(text("UPDATE sc_sourcing_plots SET postal_address = 'Plot 7, Ejisu Road, Kumasi' WHERE plot_id = CAST(:p AS uuid)"),
              {"p": bare})
    assert _blocking(api, maker, ent) == set()

    # the generic paths send you to the EUDR page
    assert "simplified declaration" in api.get("/v1/filings/preflight?framework=eudr_simplified", headers=maker).text

    # prepared, filed with four eyes, identified
    p = api.post("/v1/eudr/declaration/filing", headers=maker, json={"entity_id": ent, "note": "first declaration"})
    assert p.status_code == 201, p.text
    fid = p.json()["filing_id"]
    assert api.post("/v1/eudr/declaration/filing", headers=maker, json={"entity_id": ent}).status_code == 409   # one live
    v = api.get(f"/v1/filings/{fid}/validation", headers=maker).json()
    assert v["passed"], [f for f in v["findings"] if not f["passed"] and f["severity"] == "blocking"]
    _file(api, maker, checker, fid)
    acc = api.post(f"/v1/filings/{fid}/accept", headers=maker, json={"ack_ref": "x"})
    assert acc.status_code == 409 and "declaration identifier" in acc.text
    ok = api.post(f"/v1/eudr/declaration/filings/{fid}/identifier", headers=maker,
                  json={"identifier": "26GHDECL0001", "verification_number": "V1", "source": "information_system"})
    assert ok.status_code == 200 and ok.json()["status"] == "accepted", ok.text

    # the official form: Annex III as printed, with what the declaration says
    form = api.get(f"/v1/filings/{fid}/form", headers=maker).json()
    annex = next(x for x in form["annex"]["sections"] if x.get("key") == "eudr_annex_iii")
    first = [r["cells"][0]["text"] for r in annex["rows"] if r["cells"][0]["text"]]
    assert first[0].startswith("1. Micro or small primary operator’s name") and first[-1].startswith("4. The text:")
    assert any("postal address: Plot 7" in r["cells"][1]["text"] for r in annex["rows"])
    assert annex["rows"][0]["cells"][1]["text"].startswith("E115 cocoa farm")      # the declaring undertaking, not the group

    # an update after a major change keeps the identifier
    up = api.post(f"/v1/eudr/declaration/filings/{fid}/update", headers=maker, json={"note": "second product"})
    assert up.status_code == 201, up.text
    fid2 = up.json()["filing_id"]
    assert _status_of(s, fid) == "superseded"
    _file(api, maker, checker, fid2)
    other = api.post(f"/v1/eudr/declaration/filings/{fid2}/identifier", headers=maker, json={"identifier": "26GHDECL0999"})
    assert other.status_code == 409 and "keeps the declaration identifier" in other.text
    assert api.post(f"/v1/eudr/declaration/filings/{fid2}/identifier", headers=maker,
                    json={"identifier": "26GHDECL0001"}).json()["status"] == "accepted"

    # used as a reference in a grouping: no longer withdrawn — the service and the database both refuse
    assert api.post(f"/v1/eudr/declaration/filings/{fid2}/events", headers=maker, json={"kind": "grouped"}).status_code == 201
    w = api.post(f"/v1/eudr/declaration/filings/{fid2}/withdraw", headers=maker, json={"reason": "no longer farming cocoa"})
    assert w.status_code == 409 and "grouping" in w.text
    import psycopg
    with pytest.raises(Exception) as e, s.begin_nested():
        s.execute(text("UPDATE regulatory_filing SET status = 'withdrawn' WHERE filing_id = CAST(:f AS uuid)"), {"f": fid2})
    assert isinstance(e.value.orig, psycopg.errors.RaiseException)

    # the authority may still reject it — Art. 8 sets no identifier limit for a declaration
    assert api.post(f"/v1/eudr/declaration/filings/{fid2}/events", headers=maker,
                    json={"kind": "rejected", "detail": "high risk confirmed"}).status_code == 201
    assert _status_of(s, fid2) == "rejected"
    hist = api.get(f"/v1/eudr/declaration?entity_id={ent}", headers=maker).json()["history"]
    assert [h["status"] for h in hist][:2] == ["rejected", "superseded"] and hist[0]["declaration_identifier"] == "26GHDECL0001"


def test_withdrawn_once_submitted_and_the_database_holds_the_rules(api):
    s = api.s
    maker, checker = _login(api, "analyst@terra.demo", "Demo!analyst1"), _login(api, "approver@terra.demo", "Demo!approve1")
    ent = _entity(s)
    _status(api, maker, checker, ent)
    _plot(s, ent, polygon=True, decimals=6)
    assert api.post("/v1/eudr/declaration/lines", headers=maker, json={"entity_id": ent, "hs_code": "180100",
                                                                       "description": "Cocoa beans", "customs_flow": True,
                                                                       "est_net_mass_kg": 5000}).status_code == 201
    fid = api.post("/v1/eudr/declaration/filing", headers=maker, json={"entity_id": ent}).json()["filing_id"]
    import psycopg
    with pytest.raises(Exception) as e, s.begin_nested():                 # not accepted without an identifier
        s.execute(text("UPDATE regulatory_filing SET status = 'submitted' WHERE filing_id = CAST(:f AS uuid)"), {"f": fid})
        s.execute(text("UPDATE regulatory_filing SET status = 'accepted' WHERE filing_id = CAST(:f AS uuid)"), {"f": fid})
    assert isinstance(e.value.orig, psycopg.errors.RaiseException)
    _file(api, maker, checker, fid)
    w = api.post(f"/v1/eudr/declaration/filings/{fid}/withdraw", headers=maker, json={"reason": "stopped selling cocoa"})
    assert w.status_code == 200 and _status_of(s, fid) == "withdrawn", w.text
