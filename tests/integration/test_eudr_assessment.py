"""EUDR layer 3 (E94): the reading of a plot, the legality evidence and the operator's assessment — each kept, the
assessment with four eyes. One rolled-back transaction (Terra Foods); the satellite engine is stubbed (the raster read
itself is services.intelligence.forest, tested on its own).

  reading     loss after 31.12.2020 is a reading ('loss_after_cutoff'), never a verdict; a point plot without a stated
              radius, or a plot across data tiles, is 'not assessable' with the reason; a stated canopy threshold is
              recorded with the reading; a plot redrawn after its reading has no current reading
  evidence    one plot, supplier or movement and one Art. 2(40) aspect; a withdrawn document no longer counts
  assessment  the full path answers every Art. 10(2) criterion; a second person approves; the latest is the live one
  status      the operator's address is required (Annex II point 1); four eyes
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from services.eudr import reading as RD
from services.eudr import records as REC
from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration
TERRA = "55555555-5555-4555-8555-555555555555"
SQUARE = {"type": "Polygon", "coordinates": [[[-1.606, 6.694], [-1.604, 6.694], [-1.604, 6.696], [-1.606, 6.696], [-1.606, 6.694]]]}


def _fake_loss(pixels_unmasked: int, pixels_masked: int):
    def f(footprint, cutoff_year, min_treecover_pct, point_buffer_m, **_):
        n = pixels_masked if min_treecover_pct else pixels_unmasked
        return SimpleNamespace(insufficient=False, loss_pixels=n, total_pixels=400, loss_ha=round(n * 0.09, 4),
                               first_loss_year=2022 if n else None, tile="10N_010W", source="GFC-test (staged)",
                               forest_pixels=300)
    return f


def _plot(s, geometry=None) -> str:
    return str(s.execute(text("""
        INSERT INTO sc_sourcing_plots (org_id, plot_name, latitude, longitude, country, plot_geometry, commodity_id)
        VALUES (CAST(:o AS uuid), 'E94 plot', 6.695, -1.605, 'GH', CAST(:g AS jsonb),
                (SELECT commodity_id FROM sc_commodities WHERE name = 'Cocoa'))
        RETURNING plot_id"""), {"o": TERRA, "g": json.dumps(geometry) if geometry else None}).scalar())


def test_a_reading_is_kept_and_never_a_verdict(session_rolled_back, monkeypatch):
    from services.intelligence import forest
    s = session_rolled_back
    monkeypatch.setattr(forest, "forest_loss_since", _fake_loss(5, 0))
    poly, point = _plot(s, SQUARE), _plot(s)
    r = RD.record(s, TERRA, poly, None)
    assert r["outcome"] == "loss_after_cutoff" and r["first_loss_year"] == 2022 and r["method"]["treecover_min_pct"] is None
    r = RD.record(s, TERRA, poly, None, treecover_min_pct=30)            # loss only on non-forest pixels: none on 2000 forest
    assert r["outcome"] == "no_loss_detected" and r["method"]["loss_pixels_unmasked"] == 5
    r = RD.record(s, TERRA, point, None)
    assert r["outcome"] == "not_assessable" and "a point has no area" in r["reason"]
    assert RD.current(s, [poly])[poly]["outcome"] == "no_loss_detected"   # the latest of its current geometry
    s.execute(text("UPDATE sc_sourcing_plots SET plot_geometry = CAST(:g AS jsonb) WHERE plot_id = CAST(:p AS uuid)"),
              {"g": json.dumps({**SQUARE, "coordinates": [[[x + 0.001, y] for x, y in SQUARE["coordinates"][0]]]}), "p": poly})
    assert RD.current(s, [poly])[poly] is None                            # redrawn: read it again
    wide = {"type": "Polygon", "coordinates": [[[-0.01, 9.99], [0.01, 9.99], [0.01, 10.01], [-0.01, 10.01], [-0.01, 9.99]]]}
    assert RD.read(wide, treecover_min_pct=None, point_radius_m=None)["outcome"] == "not_assessable"


def test_legality_evidence_and_the_assessment_are_kept_with_four_eyes(api):
    s = api.s
    maker, checker = _login(api, "analyst@terra.demo", "Demo!analyst1"), _login(api, "approver@terra.demo", "Demo!approve1")
    plot = _plot(s, SQUARE)
    # a reporting entity of the test's own: the organisation's own EUDR status (demo data) never decides what it sees (E81)
    ent = str(s.execute(text("""INSERT INTO reporting_entities (entity_id, org_id, name) VALUES (gen_random_uuid(),
                                CAST(:o AS uuid), 'E94 importer') RETURNING entity_id"""), {"o": TERRA}).scalar())
    m = str(s.execute(text("""INSERT INTO eudr_movement (org_id, kind, actor_role, planned_on, hs_code, description, customs_flow,
                                                         net_mass_kg, reporting_entity_id) VALUES (CAST(:o AS uuid), 'placing',
                                                         'operator', '2027-01-15', '180100', 'Cocoa beans', true, 1000,
                                                         CAST(:e AS uuid)) RETURNING movement_id"""),
                      {"o": TERRA, "e": ent}).scalar())
    s.execute(text("INSERT INTO eudr_movement_plot VALUES (CAST(:m AS uuid), CAST(:p AS uuid), '2026-01-01', '2026-06-30')"),
              {"m": m, "p": plot})

    # status: the address is required; four eyes
    bad = api.post("/v1/eudr/status", headers=maker, json={"effective_from": "2026-12-30", "size_class": "large", "country": "ES",
                                                          "address": "", "eori": "ESB12345678"})
    assert bad.status_code == 422
    r = api.post("/v1/eudr/status", headers=maker, json={"effective_from": "2026-12-30", "size_class": "large", "country": "ES",
                                                        "address": "Calle Mayor 1, Madrid", "eori": "ESB12345678"})
    assert r.status_code == 202, r.text
    assert api.post(f"/v1/approvals/{r.json()['approval_request_id']}/decide", headers=maker,
                    json={"decision": "approved"}).status_code in (403, 422)
    assert api.post(f"/v1/approvals/{r.json()['approval_request_id']}/decide", headers=checker,
                    json={"decision": "approved", "reason": "checked"}).status_code == 200
    from datetime import date
    assert REC.live_status(s, TERRA, None, date(2027, 1, 15))["eori"] == "ESB12345678"

    # evidence: one subject, an Art. 2(40) aspect; a withdrawn document no longer counts
    assert api.post("/v1/eudr/evidence", headers=maker, json={"aspect": "beauty", "document_kind": "x", "plot_id": plot}).status_code == 422
    e = api.post("/v1/eudr/evidence", headers=maker, json={"aspect": "land_use_rights", "document_kind": "Land title",
                                                          "plot_id": plot, "document_ref": "GH-LT-001"})
    assert e.status_code == 201, e.text
    on = date(2027, 1, 15)
    assert [x["aspect"] for x in REC.evidence_for(s, TERRA, plot_ids=[plot], supplier_ids=[], movement_id=m, on=on)] == ["land_use_rights"]
    api.post("/v1/eudr/evidence", headers=maker, json={"aspect": "land_use_rights", "document_kind": "withdrawal",
                                                      "plot_id": plot, "withdraws": e.json()["evidence_id"]})
    assert REC.evidence_for(s, TERRA, plot_ids=[plot], supplier_ids=[], movement_id=m, on=on) == []

    # the assessment: every Art. 10(2) criterion answered; four eyes; the latest is live
    part = api.post(f"/v1/eudr/movements/{m}/risk-assessment", headers=maker,
                    json={"path": "full", "conclusion": "negligible", "criteria": {"a": "Ghana: low risk"}})
    assert part.status_code == 422 and "(b)" in part.text
    full = {k: f"assessed: {k}" for k in REC.CRITERIA}
    r = api.post(f"/v1/eudr/movements/{m}/risk-assessment", headers=maker,
                 json={"path": "full", "conclusion": "negligible", "criteria": full, "mitigation": {"a": "plot titles obtained"}})
    assert r.status_code == 202, r.text
    assert REC.live_assessment(s, m) is None                               # not until a second person approves
    api.post(f"/v1/approvals/{r.json()['approval_request_id']}/decide", headers=checker, json={"decision": "approved", "reason": "ok"})
    live = REC.live_assessment(s, m)
    assert live["conclusion"] == "negligible" and live["requested_by"] == "analyst@terra.demo" and live["approved_by"] == "approver@terra.demo"


def test_the_statement_gathers_what_annex_ii_and_art_9_ask(api, monkeypatch):
    from services.intelligence import forest
    monkeypatch.setattr(forest, "forest_loss_since", _fake_loss(0, 0))
    s = api.s
    maker = _login(api, "analyst@terra.demo", "Demo!analyst1")
    gh, ci = _plot(s, SQUARE), _plot(s, SQUARE)
    s.execute(text("UPDATE sc_sourcing_plots SET country = 'CI' WHERE plot_id = CAST(:p AS uuid)"), {"p": ci})
    # a reporting entity of the test's own: the organisation's own EUDR status (demo data) never decides what it sees (E81)
    ent = str(s.execute(text("""INSERT INTO reporting_entities (entity_id, org_id, name) VALUES (gen_random_uuid(),
                                CAST(:o AS uuid), 'E94 importer') RETURNING entity_id"""), {"o": TERRA}).scalar())
    m = str(s.execute(text("""INSERT INTO eudr_movement (org_id, kind, actor_role, planned_on, hs_code, description, customs_flow,
                                                         net_mass_kg, reporting_entity_id) VALUES (CAST(:o AS uuid), 'placing',
                                                         'operator', '2027-01-15', '180100', 'Cocoa beans', true, 1000,
                                                         CAST(:e AS uuid)) RETURNING movement_id"""),
                      {"o": TERRA, "e": ent}).scalar())
    s.execute(text("INSERT INTO eudr_movement_plot VALUES (CAST(:m AS uuid), CAST(:p AS uuid), '2026-01-01', '2026-06-30')"),
              {"m": m, "p": gh})
    RD.record(s, TERRA, gh, None)

    st = api.get(f"/v1/eudr/movements/{m}/statement", headers=maker).json()
    assert st["scope"]["in_scope"] is True and st["annex_ii"]["2"]["hs_code"] == "180100"
    assert st["annex_ii"]["3"]["countries"] == ["GH"] and st["countries"] == {"GH": "low"}
    assert st["plots"][0]["reading"]["outcome"] == "no_loss_detected" and st["annex_ii"]["5"].startswith("By submitting")
    assert st["annex_ii"]["1"]["address"] is None                     # no status stated yet: shown, not invented

    # Art. 13: the simplified path only where every country of production is low risk, with circumvention / mixing assessed
    simple = {"path": "simplified", "conclusion": "negligible", "circumvention_mixing": "single-origin cooperative, sealed lots"}
    assert api.post(f"/v1/eudr/movements/{m}/risk-assessment", headers=maker, json={**simple, "circumvention_mixing": ""}).status_code == 422
    r = api.post(f"/v1/eudr/movements/{m}/risk-assessment", headers=maker, json=simple)
    assert r.status_code == 202, r.text
    s.execute(text("INSERT INTO eudr_movement_plot VALUES (CAST(:m AS uuid), CAST(:p AS uuid), '2026-01-01', '2026-06-30')"),
              {"m": m, "p": ci})                                    # a plot in a standard-risk country joins the movement
    r = api.post(f"/v1/eudr/movements/{m}/risk-assessment", headers=maker, json=simple)
    assert r.status_code == 422 and "not low risk: CI" in r.text
