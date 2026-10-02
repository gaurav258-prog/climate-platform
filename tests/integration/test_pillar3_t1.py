"""Pillar 3 Template 1 columns i-k to the instructions (E103) and Template 5 cells traced to their exposures (E105) — end to
end through the HTTP API on the demo bank (Meridian), inside one rolled-back transaction. Every fact the figures read is
stated here: the demo book's emissions facts are set aside first, then two exposures state theirs (E81/E85).
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from services.calc_settings import upsert_calc_settings
from services.governance import pillar3_t1 as T1
from tests.integration.conftest import login as _login
from tests.integration.test_intake_pipeline import BANK_ORG
from tests.integration.test_pillar3_report import _new_filing, _payload

pytestmark = pytest.mark.integration
ADMIN = ("admin@meridian.demo", "Demo!admin1")
STATED = {"a": {"ghg": (100.0, 50.0, 1_000.0), "L": 2_000_000_000.0, "rep": True},
          "b": {"ghg": (40.0, 10.0, 400.0), "L": 500_000_000.0, "rep": False}}


def _two_exposures(s) -> dict:
    """Set aside the demo book's emissions facts; two non-financial-corporate exposures state theirs."""
    s.execute(text("""UPDATE ext_banking x SET ghg_emissions_scope1_tco2e = NULL, ghg_emissions_scope2_tco2e = NULL,
                      ghg_emissions_scope3_tco2e = NULL, counterparty_total_liabilities_eur = NULL,
                      counterparty_total_liabilities_date = NULL, emissions_company_reported = NULL
                      FROM portfolio_entities e WHERE e.entity_id = x.entity_id AND e.org_id = CAST(:o AS uuid)"""),
              {"o": BANK_ORG})
    ids = [r[0] for r in s.execute(text("""
        SELECT e.entity_id::text FROM portfolio_entities e JOIN ext_banking x ON x.entity_id = e.entity_id
        WHERE e.org_id = CAST(:o AS uuid) AND e.vertical = 'banking' AND x.outstanding_loan_balance_eur > 0
        ORDER BY e.entity_id LIMIT 2"""), {"o": BANK_ORG})]
    out = {}
    for key, eid in zip(STATED, ids):
        st = STATED[key]
        s.execute(text("UPDATE portfolio_entities SET nace_code = 'C24.10' WHERE entity_id = CAST(:e AS uuid)"), {"e": eid})
        s.execute(text("""UPDATE ext_banking SET counterparty_sector = 'non_financial_corporation',
                          ghg_emissions_scope1_tco2e = :g1, ghg_emissions_scope2_tco2e = :g2, ghg_emissions_scope3_tco2e = :g3,
                          counterparty_total_liabilities_eur = :L, counterparty_total_liabilities_date = DATE '2025-12-31',
                          emissions_company_reported = :rep WHERE entity_id = CAST(:e AS uuid)"""),
                  {"e": eid, "g1": st["ghg"][0], "g2": st["ghg"][1], "g3": st["ghg"][2], "L": st["L"], "rep": st["rep"]})
        out[eid] = st
    assert len(out) == 2
    return out


def _state(s, est, att):
    upsert_calc_settings(s, BANK_ORG, {T1.ESTIMATION: est, T1.ATTRIBUTION: att}, None)


def _findings(api, h, fid) -> dict:
    r = api.get(f"/v1/filings/{fid}/validation", headers=h)
    assert r.status_code == 200, r.text
    return {f["rule"]: f for f in r.json()["findings"]}


def test_the_switches_are_offered_with_their_quotes_and_refuse_anything_else(api):
    h = _login(api, *ADMIN)
    cat = {c["key"]: c for c in api.get("/v1/calc-settings/catalog", headers=h).json()["interpretation"]}
    assert cat[T1.ATTRIBUTION]["default"] is None and cat[T1.ATTRIBUTION]["allowed"] == ["exposure_over_total_liabilities"]
    assert "total liabilities (accounting liabilities and shareholders’ equity)" in cat[T1.ATTRIBUTION]["description"]
    assert cat[T1.ESTIMATION]["allowed"] == ["scope_1_2_3", "scope_1_2", "not_yet_estimating"]
    r = api.patch("/v1/calc-settings", headers=h, json={"interpretation": {T1.ATTRIBUTION: "pcaf"}})
    assert r.status_code == 422


def test_total_liabilities_are_stated_per_exposure_with_their_balance_sheet_date(api):
    h = _login(api, *ADMIN)
    s = api.s
    eid = s.execute(text("""SELECT e.entity_id::text FROM portfolio_entities e JOIN ext_banking x ON x.entity_id = e.entity_id
                            WHERE e.org_id = CAST(:o AS uuid) AND e.vertical = 'banking' AND e.source = 'own'
                            ORDER BY e.entity_id LIMIT 1"""), {"o": BANK_ORG}).scalar()
    ref = "TEST-P3-T1-REF"                                     # the asset ID this test gives it (stated here)
    s.execute(text("UPDATE portfolio_entities SET external_ref = :r WHERE entity_id = CAST(:e AS uuid)"), {"r": ref, "e": eid})
    csv = f"external_ref,counterparty_total_liabilities_eur,currency,book_date\n{ref},420000000,EUR,2025-12-31\n".encode()
    r = api.post("/v1/bank/assets/attributes/upload", headers=h, files={"file": ("attrs.csv", csv)})
    assert r.status_code == 200 and r.json()["n_updated"] == 1, r.text
    v, d, ms = s.execute(text("""SELECT CAST(counterparty_total_liabilities_eur AS FLOAT), counterparty_total_liabilities_date,
                                 money_source FROM ext_banking WHERE entity_id = CAST(:e AS uuid)"""), {"e": eid}).first()
    assert v == 420_000_000 and str(d) == "2025-12-31"
    assert ms["fields"]["counterparty_total_liabilities_eur"]["amount"] == 420_000_000
    bad = f"external_ref,counterparty_total_liabilities_eur,currency,book_date\n{ref},-5,EUR,2025-12-31\n".encode()
    r = api.post("/v1/bank/assets/attributes/upload", headers=h, files={"file": ("attrs.csv", bad)})
    assert r.status_code == 400                                  # a negative amount never passes the file's checks
    assert s.execute(text("SELECT CAST(counterparty_total_liabilities_eur AS FLOAT) FROM ext_banking WHERE entity_id = "
                          "CAST(:e AS uuid)"), {"e": eid}).scalar() == 420_000_000


def test_a_pillar3_filing_prints_columns_i_to_k_on_the_stated_method(api):
    h = _login(api, *ADMIN)
    s = api.s
    stated = _two_exposures(s)

    # set aside whatever the organisation has stated and authored for Template 1
    s.execute(text("UPDATE org_calc_settings SET interpretation = interpretation - :a - :b WHERE org_id = CAST(:o AS uuid)"),
              {"a": T1.ESTIMATION, "b": T1.ATTRIBUTION, "o": BANK_ORG})
    s.execute(text("""DELETE FROM template_answers WHERE org_id = CAST(:o AS uuid) AND family = 'bank_p3esg'
                      AND item_id LIKE 't1.%'"""), {"o": BANK_ORG})

    # nothing stated: the columns are a gap and the filing is blocked
    fid = _new_filing(api, h)
    f = _findings(api, h, fid)
    assert not f["t1_method_stated"]["passed"] and f["t1_method_stated"]["severity"] == "blocking"
    dps = {d["key"]: d for g in api.get(f"/v1/filings/{fid}/form", headers=h).json()["groups"] for d in g["datapoints"]}
    assert dps["emissions.total"]["value"] is None and "not stated" in dps["emissions.total"]["note"]

    # stated: scopes 1-3, attributed by the exposure over total liabilities; the narrative not yet authored → blocked
    _state(s, "scope_1_2_3", "exposure_over_total_liabilities")
    fid = _new_filing(api, h)
    f = _findings(api, h, fid)
    assert f["t1_method_stated"]["passed"] and not f["t1_narrative_authored"]["passed"]

    # the narrative, authored through the qualitative disclosures
    body = {"values": {n["key"]: f"Our {n['key']}" for n in T1.required_narrative("scope_1_2_3")}}
    r = api.patch("/v1/filings/qualitative/p3esg", headers=h, json=body)
    assert r.status_code == 200, r.text
    assert {row["key"] for t in r.json()["tables"] for row in t["rows"]} >= set(body["values"])
    fid = _new_filing(api, h)
    p = _payload(s, fid)
    assert p[T1.RECORD]["estimation"] == "scope_1_2_3" and set(p[T1.RECORD]["narrative"]) == set(body["values"])
    f = _findings(api, h, fid)
    assert all(f[k]["passed"] for k in ("t1_method_stated", "t1_total_liabilities_stated", "t1_exposure_within_liabilities",
                                        "t1_emissions_source_recorded", "t1_narrative_authored")), f

    # the figures: Σ gross carrying amount ÷ total liabilities × emissions, over the two stating exposures (as frozen)
    frozen = {a["asset_id"]: a for a in p["assets"]}
    want_i = sum(frozen[e]["outstanding_loan_balance_eur"] / frozen[e]["counterparty_total_liabilities_eur"] * sum(st["ghg"])
                 for e, st in stated.items())
    want_j = sum(frozen[e]["outstanding_loan_balance_eur"] / frozen[e]["counterparty_total_liabilities_eur"] * st["ghg"][2]
                 for e, st in stated.items())
    form = api.get(f"/v1/filings/{fid}/form", headers=h).json()
    dps = {d["key"]: d for g in form["groups"] for d in g["datapoints"]}
    assert dps["emissions.total"]["value"] == pytest.approx(want_i, rel=1e-9)
    assert dps["emissions.scope3"]["value"] == pytest.approx(want_j, rel=1e-9)
    assert dps["emissions.company_reported_pct"]["value"] is not None
    t1 = next(x for x in form["annex"]["sections"] if x.get("key") == "t1")
    assert "Our t1.methodology" in t1["note"] and "total liabilities" in t1["note"]

    # scope 3 not yet estimated: column j is left blank, column i is scopes 1 and 2
    _state(s, "scope_1_2", "exposure_over_total_liabilities")
    api.patch("/v1/filings/qualitative/p3esg", headers=h, json={"values": {"t1.plans_scope3": "From 2027"}})
    fid = _new_filing(api, h)
    dps = {d["key"]: d for g in api.get(f"/v1/filings/{fid}/form", headers=h).json()["groups"] for d in g["datapoints"]}
    assert dps["emissions.scope3"]["value"] is None
    want_12 = sum(frozen[e]["outstanding_loan_balance_eur"] / frozen[e]["counterparty_total_liabilities_eur"]
                  * (st["ghg"][0] + st["ghg"][1]) for e, st in stated.items())
    assert dps["emissions.total"]["value"] == pytest.approx(want_12, rel=1e-9)


def test_template5_cells_trace_to_the_exposures_they_sum(api):
    h = _login(api, *ADMIN)
    fid = _new_filing(api, h)
    v = api.get(f"/v1/filings/{fid}/lineage/t5", headers=h).json()
    assert v["supported"] and v["columns"][0]["id"] == "b" and v["geographies"][0]["code"] == "ALL"
    p = _payload(api.s, fid)
    ids = {a["asset_id"] for a in p["assets"]}
    traced = 0
    for geo in [g["code"] for g in v["geographies"]][:3]:
        for row in v["rows"]:
            for col in ("b", "h", "i", "j", "g"):
                if not v["cells"][geo][row["id"]].get(col):
                    continue
                t = api.get(f"/v1/filings/{fid}/lineage/t5/cell", headers=h,
                            params={"row": row["id"], "column": col, "geography": geo}).json()
                assert t["supported"] and t["cell"]["ties"], (geo, row["id"], col, t["cell"])
                assert t["cell"]["printed"] == v["cells"][geo][row["id"]][col]
                assert {c["asset_id"] for c in t["contributors"]} <= ids
                if col in ("h", "i", "j"):
                    cats = {"h": {"chronic"}, "i": {"acute"}, "j": {"chronic", "acute"}}[col]
                    assert all({x["category"] for x in c["hazards"]} == cats for c in t["contributors"])
                traced += 1
    assert traced                                                        # the book has sensitive exposures to trace
    assert api.get(f"/v1/filings/{fid}/lineage/t5/cell", headers=h,
                   params={"row": "1", "column": "a"}).status_code == 404          # column a is the geography itself
    old = api.get(f"/v1/filings/{fid}/lineage", headers=h, params={"hazard": "flood"}).json()
    assert not old["supported"] and "lineage/t5" in old["message"]
