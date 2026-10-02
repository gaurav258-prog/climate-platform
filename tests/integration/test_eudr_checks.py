"""EUDR layer 4 (E107): the checks a due diligence statement must pass, each with its article — from nothing on file to
ready, through the HTTP API in one rolled-back transaction (Terra Foods; the satellite engine stubbed).

  blocking first   no status, no plots, no supplier identity, no legality evidence, no risk assessment
  plots            fewer than six decimals; over four hectares without a polygon (Art. 2(28))
  scope            an HS code outside Annex I; an 'ex' heading left open until the operator states its product's scope
  who files        a trader files no statement (Art. 5)
  ready            every blocking check passes once each record is in place
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from services.eudr import reading as RD
from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration
TERRA = "55555555-5555-4555-8555-555555555555"
SQUARE = {"type": "Polygon", "coordinates": [[[-1.606123, 6.694123], [-1.604123, 6.694123], [-1.604123, 6.696123],
                                              [-1.606123, 6.696123], [-1.606123, 6.694123]]]}


def _no_loss(footprint, cutoff_year, min_treecover_pct, point_buffer_m, **_):
    return SimpleNamespace(insufficient=False, loss_pixels=0, total_pixels=400, loss_ha=0.0, first_loss_year=None,
                           tile="10N_010W", source="GFC-test", forest_pixels=300)


def _blocking(st) -> set[str]:
    return {c["rule"].split(":")[0] for c in st["checks"] if not c["passed"] and c["severity"] == "blocking"}


def _entity(s) -> str:
    """A reporting entity of the test's own: the organisation's own EUDR status (demo data, a walkthrough) never decides
    what this test sees (E81)."""
    return str(s.execute(text("""INSERT INTO reporting_entities (entity_id, org_id, name) VALUES (gen_random_uuid(), CAST(:o AS uuid), 'E107 importer')
                                 RETURNING entity_id"""), {"o": TERRA}).scalar())


def _movement(s, hs="180100", role="operator", supplier=None, entity=None) -> str:
    return str(s.execute(text("""
        INSERT INTO eudr_movement (org_id, kind, actor_role, planned_on, hs_code, description, customs_flow, net_mass_kg, supplier_id,
                                   reporting_entity_id)
        VALUES (CAST(:o AS uuid), 'placing', :r, '2027-01-15', :hs, 'Cocoa beans', true, 1000, CAST(:s AS uuid), CAST(:e AS uuid))
        RETURNING movement_id"""), {"o": TERRA, "r": role, "hs": hs, "s": supplier, "e": entity}).scalar())


def _plot(s, decimals=6, area=2.0, polygon=True) -> str:
    return str(s.execute(text("""
        INSERT INTO sc_sourcing_plots (org_id, plot_name, latitude, longitude, country, plot_geometry, plot_area_ha,
                                       coordinate_decimals, commodity_id)
        VALUES (CAST(:o AS uuid), 'E107 plot', 6.695123, -1.605123, 'GH', CAST(:g AS jsonb), :a, :d,
                (SELECT commodity_id FROM sc_commodities WHERE name = 'Cocoa')) RETURNING plot_id"""),
        {"o": TERRA, "g": json.dumps(SQUARE) if polygon else None, "a": area, "d": decimals}).scalar())


def _link(s, m, p):
    s.execute(text("INSERT INTO eudr_movement_plot VALUES (CAST(:m AS uuid), CAST(:p AS uuid), '2026-01-01', '2026-06-30')"),
              {"m": m, "p": p})


def _approve(api, checker, r):
    assert r.status_code == 202, r.text
    d = api.post(f"/v1/approvals/{r.json()['approval_request_id']}/decide", headers=checker, json={"decision": "approved", "reason": "ok"})
    assert d.status_code == 200, d.text


def test_a_statement_is_blocked_until_each_record_is_in_place(api, monkeypatch):
    from services.intelligence import forest
    monkeypatch.setattr(forest, "forest_loss_since", _no_loss)
    s = api.s
    maker, checker = _login(api, "analyst@terra.demo", "Demo!analyst1"), _login(api, "approver@terra.demo", "Demo!approve1")
    ent = _entity(s)
    m = _movement(s, entity=ent)
    get = lambda: api.get(f"/v1/eudr/movements/{m}/statement", headers=maker).json()      # noqa: E731
    assert {"annex_ii_1", "annex_ii_3", "supplier", "legality", "risk_assessment"} <= _blocking(get())

    # plots: too few decimals, over four hectares without a polygon — then a proper plot
    bad_d, big = _plot(s, decimals=4), _plot(s, area=12.0, polygon=False)
    _link(s, m, bad_d), _link(s, m, big)
    b = _blocking(get())
    assert {"decimals", "polygon"} <= b
    s.execute(text("DELETE FROM eudr_movement_plot WHERE movement_id = CAST(:m AS uuid)"), {"m": m})
    good = _plot(s)
    _link(s, m, good)
    RD.record(s, TERRA, good, None)

    # the operator's records
    sup = str(s.execute(text("""INSERT INTO sc_suppliers (org_id, name, address, contact_email) VALUES (CAST(:o AS uuid),
                               'Ashanti Co-op', 'PO Box 1, Kumasi', 'co@op.example') RETURNING supplier_id"""), {"o": TERRA}).scalar())
    s.execute(text("UPDATE eudr_movement SET supplier_id = CAST(:s AS uuid) WHERE movement_id = CAST(:m AS uuid)"), {"s": sup, "m": m})
    _approve(api, checker, api.post("/v1/eudr/status", headers=maker, json={
        "effective_from": "2026-12-30", "size_class": "large", "country": "ES", "address": "Calle Mayor 1, Madrid",
        "eori": "ESB12345678", "entity_id": ent}))
    assert api.post("/v1/eudr/evidence", headers=maker, json={"aspect": "land_use_rights", "document_kind": "Land title",
                                                             "plot_id": good}).status_code == 201
    assert _blocking(get()) == {"risk_assessment"}
    from services.eudr.records import CRITERIA
    _approve(api, checker, api.post(f"/v1/eudr/movements/{m}/risk-assessment", headers=maker, json={
        "path": "full", "conclusion": "negligible", "criteria": {k: f"assessed {k}" for k in CRITERIA}}))
    st = get()
    assert _blocking(st) == set() and any(c["rule"] == "ready" for c in st["checks"])
    assert next(c for c in st["checks"] if c["rule"] == "application")["passed"]


def test_scope_and_who_files(api):
    s = api.s
    maker = _login(api, "analyst@terra.demo", "Demo!analyst1")
    out = _movement(s, hs="0401")                                       # milk: not in Annex I
    assert "scope" in _blocking(api.get(f"/v1/eudr/movements/{out}/statement", headers=maker).json())
    ex = _movement(s, hs="151110")                                      # 'ex 1511' (palm oil) on 2027-01-15: left to the operator
    st = api.get(f"/v1/eudr/movements/{ex}/statement", headers=maker).json()
    assert st["scope"]["in_scope"] is None and "scope" in _blocking(st)
    r = api.put(f"/v1/eudr/movements/{ex}/scope", headers=maker, json={"in_scope": True, "basis": "crude palm oil from Elaeis"})
    assert r.status_code == 200, r.text
    assert "scope" not in _blocking(api.get(f"/v1/eudr/movements/{ex}/statement", headers=maker).json())
    assert api.put(f"/v1/eudr/movements/{out}/scope", headers=maker,
                   json={"in_scope": True, "basis": "trying to override the annex"}).status_code == 409
    tr = _movement(s, role="trader")
    assert "filer" in _blocking(api.get(f"/v1/eudr/movements/{tr}/statement", headers=maker).json())
