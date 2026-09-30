"""The ESRS statement's figures, worked by hand on a controlled book (rolled back):

  group      parent P (consolidated, Art. 29a) with subsidiary S (full), joint operation J (proportional, 50 %, own
             operations at the share — 2026 ESRS 1 AR 36), joint venture V (proportional — value chain, 2023 ESRS 1 §67)
             and associate A (equity method — value chain)
  sites      P1 held all year; S1 held; J1 held (counts 50 %); A1 held (excluded); P2 disposed before the period end;
             P3 acquired after it — only P1, S1, J1 are in the book at 31.12.2025
  hazards    synthetic cells: P1 flood 70 (acute) today; S1 drought (acute in EU Taxonomy Appendix A) 40 today, 55 by 2030, 62 by
             2050 under SSP5-8.5; J1 heat
             chronic 65 today; every site also seismic 95 (not a climate hazard) and frost 100 (a crop scale, never
             a building's level) — both ignored; the undertaking states its materiality level: 60
  figures    carrying 10m / 20m / 8m, adapted 4m on P1 only, revenue 30m / 50m / 12m; total assets 200m and net
             revenue 400m attested for the group
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from services.governance import esrs_statement as E

pytestmark = pytest.mark.integration
ORG = "0bbe0bbe-0000-4000-8000-0000000e5a01"
PE = date(2025, 12, 31)
CELLS = {"P1": "8a0000000000001", "S1": "8a0000000000002", "J1": "8a0000000000003", "A1": "8a0000000000004",
         "P2": "8a0000000000005", "P3": "8a0000000000006", "V1": "8a0000000000007"}


def _score(s, cell, hazard, scenario, horizon, score, model="test-v1"):
    s.execute(text("""INSERT INTO canonical_scores (h3_cell, hazard_type, scenario, time_horizon, risk_score, risk_bucket,
                                                    model_version, data_vintage)
                      VALUES (:c, :h, :s, :t, :r, 'H', :m, now())"""),
              {"c": cell, "h": hazard, "s": scenario, "t": horizon, "r": score, "m": model})


@pytest.fixture()
def book(session_rolled_back):
    s = session_rolled_back
    s.execute(text("INSERT INTO organizations (org_id, name, type, country) VALUES (CAST(:o AS uuid), 'esrs calc probe', 'manufacturer', 'DE')"),
              {"o": ORG})
    ent = {}
    for name, parent, method, pct, ja in (("P", None, "full", 100, None), ("S", "P", "full", 100, None),
                                          ("J", "P", "proportional", 50, "joint_operation"),
                                          ("V", "P", "proportional", 50, "joint_venture"), ("A", "P", "equity", 30, None)):
        ent[name] = str(uuid.uuid4())
        s.execute(text("""INSERT INTO reporting_entities (entity_id, org_id, name, parent_entity_id, consolidation_method,
                                                          ownership_pct, joint_arrangement)
                          VALUES (CAST(:e AS uuid), CAST(:o AS uuid), :n, CAST(:p AS uuid), :m, :pct, :ja)"""),
                  {"e": ent[name], "o": ORG, "n": f"{name} probe", "p": ent.get(parent), "m": method, "pct": pct, "ja": ja})
    held = {"P1": ("P", None, None), "S1": ("S", None, None), "J1": ("J", None, None), "A1": ("A", None, None),
            "V1": ("V", None, None),
            "P2": ("P", None, "2025-06-30"), "P3": ("P", "2026-02-01", None)}
    site = {}
    for key, (e, hf, hu) in held.items():
        site[key] = s.execute(text("""INSERT INTO sc_company_sites (org_id, name, entity_id, h3_cell, latitude, longitude,
                                                                     held_from, held_until, area_ha)
                                      VALUES (CAST(:o AS uuid), :n, CAST(:e AS uuid), :c, 0, 0, :hf, :hu, 10)
                                      RETURNING site_id::text"""),
                              {"o": ORG, "n": key, "e": ent[e], "c": CELLS[key], "hf": hf, "hu": hu}).scalar()
    for key, (ca, ad, rv) in {"P1": (10e6, 4e6, 30e6), "S1": (20e6, None, 50e6), "J1": (8e6, None, 12e6),
                              "A1": (99e6, None, 99e6), "V1": (77e6, None, 77e6)}.items():
        for m, v in (("carrying_amount", ca), ("carrying_amount_adapted", ad), ("net_revenue", rv)):
            if v is not None:
                s.execute(text("""INSERT INTO site_period_values (org_id, site_id, reporting_entity_id, period_end, measure,
                                                                  amount, currency, amount_eur, source)
                                  VALUES (CAST(:o AS uuid), CAST(:s AS uuid), CAST(:e AS uuid), :pe, :m, :a, 'EUR', :a, 'client')"""),
                          {"o": ORG, "s": site[key], "e": ent[held[key][0]], "pe": PE, "m": m, "a": v})
    for key in CELLS:
        for sc, th in (("baseline", "current"), ("hot_house_3_5c", "2030"), ("hot_house_3_5c", "2050")):
            _score(s, CELLS[key], "seismic", sc, th, 95)
            _score(s, CELLS[key], "frost", sc, th, 100)
    _score(s, CELLS["P1"], "flood", "baseline", "current", 70)
    _score(s, CELLS["P1"], "flood", "hot_house_3_5c", "2030", 72)
    _score(s, CELLS["P1"], "flood", "hot_house_3_5c", "2050", 75)
    _score(s, CELLS["S1"], "drought", "baseline", "current", 40)
    _score(s, CELLS["S1"], "drought", "hot_house_3_5c", "2030", 55)
    _score(s, CELLS["S1"], "drought", "hot_house_3_5c", "2050", 62)
    _score(s, CELLS["J1"], "heat_chronic", "baseline", "current", 65)
    _score(s, CELLS["J1"], "heat_chronic", "hot_house_3_5c", "2030", 70)
    _score(s, CELLS["J1"], "heat_chronic", "hot_house_3_5c", "2050", 80)
    u1, u2 = str(uuid.uuid4()), str(uuid.uuid4())
    s.execute(text("""INSERT INTO csrd_reporting_role (org_id, reporting_entity_id, period_end, role, requested_by, approved_by)
                      VALUES (CAST(:o AS uuid), CAST(:e AS uuid), :pe, 'consolidated', CAST(:a AS uuid), CAST(:b AS uuid))"""),
              {"o": ORG, "e": ent["P"], "pe": PE, "a": u1, "b": u2})
    for key, v in (("fs.total_assets", 200e6), ("fs.net_revenue", 400e6), ("esrs.method.physical_risk_level", 60)):
        s.execute(text("""INSERT INTO provided_datapoint (org_id, framework, datapoint_key, value_num, source, reporting_period_end,
                                                          reporting_entity_id, status, value_currency, value_eur, decided_at)
                          VALUES (CAST(:o AS uuid), 'esrs', :k, :v, 'client', :pe, CAST(:e AS uuid), 'attested', :c, :ve, now())"""),
                  {"o": ORG, "k": key, "v": v, "pe": PE, "e": ent["P"], "c": None if key.startswith("esrs.") else "EUR",
                   "ve": None if key.startswith("esrs.") else v})
    from services.reference.protected_layers import load_layer
    load_layer(s, "natura2000", "2025-12-31", "probe", [{"h3_cell": CELLS["S1"], "within_km": 0.0},
                                                        {"h3_cell": CELLS["P1"], "within_km": 1.0}], 8)   # P1 only 'near'
    load_layer(s, "osm", "2025-12-31", "probe", [{"h3_cell": CELLS["J1"], "within_km": 0.0}], 8)          # not a listed kind
    return s, ent


def test_the_group_statement_from_the_book_as_at_the_period_end(book):
    s, ent = book
    out = E.compute(s, ORG, entity_id=ent["P"], period_end=PE, esrs_version="dr_2023_2772_as_2025_1416")
    names = sorted(x["name"] for x in out["sites"])
    assert names == ["J1", "P1", "S1"]   # A1 associate, V1 joint venture (value chain), P2 disposed, P3 not yet acquired
    assert {x["name"]: x["weight"] for x in out["sites"]} == {"P1": 1.0, "S1": 1.0, "J1": 0.5}
    c = out["concepts"]
    # short term: P1 flood 70 (acute) + J1 heat 65 (chronic, 50 %); S1 drought 40 < 60. Seismic and frost never count.
    # medium: S1's drought 55 is still below 60; long: 62 — S1 is at material risk only in the long term
    assert c["e1.physrisk.assets.amount"]["by_horizon"] == {"short": 14e6, "medium": 14e6, "long": 34e6}
    assert c["e1.physrisk.assets.acute"]["by_horizon"] == {"short": 10e6, "medium": 10e6, "long": 30e6}
    assert c["e1.physrisk.assets.chronic"]["by_horizon"] == {"short": 4e6, "medium": 4e6, "long": 4e6}
    assert c["e1.physrisk.assets.pct"]["by_horizon"]["short"] == 7.0              # 14m / 200m
    assert c["e1.physrisk.revenue.amount"]["by_horizon"]["short"] == 36e6         # 30m + 50 % of 12m
    assert c["e1.physrisk.revenue.pct"]["by_horizon"]["long"] == 21.5             # (30 + 50 + 6) / 400
    # adaptation stated for P1 only: J1 at risk has none → a gap, not a zero
    assert c["e1.physrisk.assets.addressed_pct"]["status"] == "gap" and "not stated for J1" in c["e1.physrisk.assets.addressed_pct"]["gap"]
    # E4 §35 is the undertaking's figure; the support lists sites INSIDE a listed layer only (P1 is only 'near';
    # the OSM layer is not a kind the definition lists)
    bio = out["support"]["biodiversity_sensitive"]
    assert [x["name"] for x in bio["sites"]] == ["S1"] and "e4.sites.sensitive.count" not in c
    assert "Key Biodiversity Areas" in bio["not_assessed"]
    assert out["assessment"]["horizons"] == {"short": {"scenario": "baseline", "horizon": "current"},
                                             "medium": {"scenario": "hot_house_3_5c", "horizon": "2030"},
                                             "long": {"scenario": "hot_house_3_5c", "horizon": "2050"}}
    assert c["e1.transrisk.assets.pct"]["status"] == "gap"                         # the undertaking has not stated it


def test_an_individual_statement_is_the_undertakings_own_sites(book):
    s, ent = book
    s.execute(text("""INSERT INTO provided_datapoint (org_id, framework, datapoint_key, value_num, source, reporting_period_end,
                                                      reporting_entity_id, status, decided_at)
                      VALUES (CAST(:o AS uuid), 'esrs', 'esrs.method.physical_risk_level', 60, 'client', :pe,
                              CAST(:e AS uuid), 'attested', now())"""), {"o": ORG, "pe": PE, "e": ent["S"]})
    out = E.compute(s, ORG, entity_id=ent["S"], period_end=PE, esrs_version="dr_2023_2772_as_2025_1416")   # its own sites
    assert [x["name"] for x in out["sites"]] == ["S1"]
    assert out["concepts"]["e1.physrisk.assets.amount"]["by_horizon"] == {"short": 0, "medium": 0, "long": 20e6}


def test_what_cannot_be_established_is_a_gap_never_a_default(book):
    s, ent = book
    # the subsidiary has stated no materiality level: nothing is assessed against a platform number
    out = E.compute(s, ORG, entity_id=ent["S"], period_end=PE, esrs_version="dr_2023_2772_as_2025_1416")
    assert out["concepts"]["e1.physrisk.assets.amount"]["status"] == "gap"
    assert "has not stated the level" in out["concepts"]["e1.physrisk.assets.amount"]["gap"]
    # a proportionally consolidated entity that has not said which arrangement it is: the group figure is a gap
    s.execute(text("UPDATE reporting_entities SET joint_arrangement = NULL WHERE entity_id = CAST(:e AS uuid)"), {"e": ent["J"]})
    g = E.compute(s, ORG, entity_id=ent["P"], period_end=PE, esrs_version="dr_2023_2772_as_2025_1416")
    assert "J probe is proportionally consolidated" in g["concepts"]["e1.physrisk.assets.amount"]["gap"]
    assert "J1" not in [x["name"] for x in g["sites"]]
    # FY2030: no projection year inside the medium-term interval (2030, 2035]
    assert E.horizons(date(2030, 12, 31))["medium"] is None
