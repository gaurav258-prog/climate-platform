"""European ESG Template, end to end through the API, as two people at an asset manager:

  analyst: registers share classes → sees what the EET would hold and what's missing → can't prepare while mandatory
           fields are empty → answers them (format-checked; computed fields refused) → prepares a version
  approver: approves it (the analyst can't approve their own) → it is published → the file downloads (xlsx, csv) with
           every FinDatEx field in order, one row per ISIN, PAI figures from the book
  then:    a new share class shows as a change against the published version; a held ISIN that is an own share class
           resolves to its fund. The published version can't be altered or deleted.
Everything created is removed afterwards."""
from __future__ import annotations

import csv
import io

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from core.db.session import get_session
from tests.integration.conftest import _login

pytestmark = pytest.mark.integration
ISINS = ("LU0274208692", "IE00B4L5Y983", "DE0005140008")


@pytest.fixture()
def am():
    from fastapi.testclient import TestClient

    from api.main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        c.maker = _login(c, "analyst@nordkap.demo", "Demo!analyst1")
        c.checker = _login(c, "admin@nordkap.demo", "Demo!admin1")
        with get_session() as s:
            c.org, c.fund = s.execute(text("SELECT org_id::text, fund_id::text FROM funds WHERE name = 'Nordkap Global Equity Fund'")).first()
            # the fund's own template answers are kept exactly: the test may answer items, and puts them back after
            kept = [dict(r) for r in s.execute(text("""SELECT item_id, CAST(value AS text) AS value FROM template_answers
                                                      WHERE fund_id = CAST(:f AS uuid) AND family = 'sfdr_product'
                                                        AND document = 'precontractual'"""),
                                               {"f": c.fund}).mappings()]
        _cleanup(c.org)
        yield c
        _cleanup(c.org)
        with get_session() as s:
            s.execute(text("""DELETE FROM template_answers WHERE fund_id = CAST(:f AS uuid) AND family = 'sfdr_product'
                              AND document = 'precontractual'"""), {"f": c.fund})
            for k in kept:
                s.execute(text("""INSERT INTO template_answers (org_id, fund_id, family, document, item_id, value)
                                  VALUES (CAST(:o AS uuid), CAST(:f AS uuid), 'sfdr_product', 'precontractual', :i, CAST(:v AS jsonb))"""),
                          {"o": c.org, "f": c.fund, "i": k["item_id"], "v": k["value"]})
            s.commit()


def _cleanup(org):
    with get_session() as s:
        s.execute(text("ALTER TABLE eet_publications DISABLE TRIGGER USER"))
        s.execute(text("DELETE FROM approval_requests WHERE org_id = CAST(:o AS uuid) AND request_type = 'eet.publish'"), {"o": org})
        s.execute(text("DELETE FROM eet_publications WHERE org_id = CAST(:o AS uuid)"), {"o": org})
        s.execute(text("ALTER TABLE eet_publications ENABLE TRIGGER USER"))
        s.execute(text("DELETE FROM org_eet_answers WHERE org_id = CAST(:o AS uuid)"), {"o": org})
        s.execute(text("DELETE FROM fund_eet_answers WHERE fund_id IN (SELECT fund_id FROM funds WHERE org_id = CAST(:o AS uuid))"), {"o": org})
        s.execute(text("DELETE FROM fund_share_classes WHERE org_id = CAST(:o AS uuid)"), {"o": org})
        s.commit()


def _valid(f: dict) -> str:
    """A value that passes the field's own format — as a manager would type it."""
    k = f["kind"]
    return {"proportion": "0.25", "number": "1.5", "integer": "2", "date": "2025-12-31", "currency": "EUR",
            "codes2": "FR", "choice": (f["choices"] or ["Y"])[0], "dates": "2025-12-31"}.get(k, "https://nordkap.demo/esg")


def test_the_eet_workflow_end_to_end(am):
    c = am
    # share classes: a bad ISIN is refused, two good ones registered
    bad = c.post(f"/v1/funds/{c.fund}/share-classes", headers=c.maker,
                 json={"isin": "LU0274208693", "name": "x", "currency": "EUR", "distribution": "accumulating"})
    assert bad.status_code == 422 and "not a valid ISIN" in bad.json()["error"]["message"]
    for isin, name, ccy, hedged, dist in ((ISINS[0], "A EUR Acc", "EUR", False, "accumulating"),
                                          (ISINS[1], "B USD Dis Hedged", "USD", True, "distributing")):
        r = c.post(f"/v1/funds/{c.fund}/share-classes", headers=c.maker,
                   json={"isin": isin, "name": name, "currency": ccy, "hedged": hedged, "distribution": dist})
        assert r.status_code == 201, r.text
    dup = c.post(f"/v1/funds/{c.fund}/share-classes", headers=c.maker,
                 json={"isin": ISINS[0], "name": "again", "currency": "EUR", "distribution": "accumulating"})
    assert dup.status_code == 422 and "already registered" in dup.text

    uses = "entity,periodic,mifid"
    d = c.get(f"/v1/eet/draft?uses={uses}", headers=c.maker).json()
    assert [r["isin"] for r in d["rows"]] == [ISINS[0], ISINS[1]]
    v = d["rows"][1]["values"]
    assert v["20030_Financial_Instrument_Currency"] == "USD" and v["20040_Financial_Instrument_SFDR_Product_Type"] == "8"
    assert float(v["30040_GHG_Emissions_Scope_1_Coverage"]) <= 1 and "30180_GHG_Emissions_Total_Scope123_Value" in v
    comp = d["completeness"]
    assert not comp["ready"] and comp["n_blocking"] > 0 and all(b["answerable"] for b in comp["blocking"])
    # (every missing field can be answered — even one Tellumen computes, when the book has no figure for it)

    # can't prepare while mandatory fields are empty
    r = c.post("/v1/eet/versions", headers=c.maker, json={"uses": uses.split(",")})
    assert r.status_code == 422 and "mandatory field" in r.json()["error"]["message"]

    # answers: format-checked, computed fields refused, then every blocking field answered
    r = c.put("/v1/eet/answers", headers=c.maker, json={"fund_id": c.fund, "values": {
        "20180_Financial_Instrument_Products_Minimal_Proportion_Of_Sustainable_Investments_Art_8": "20",
        "30020_GHG_Emissions_Scope_1_Value": "1"}}).json()
    assert {x["field"] for x in r["refused"]} == {"20180_Financial_Instrument_Products_Minimal_Proportion_Of_Sustainable_Investments_Art_8"}
    assert "only while the book has no figure" in r["note"]                     # a book figure wins over a typed one
    fl = {f["name"]: f for f in c.get(f"/v1/eet/fields?uses={uses}&only=required", headers=c.maker).json()["fields"]}
    # answer what blocks, in rounds (an answer can make a conditional field required, as for a real preparer): a
    # commitment the fund's SFDR pre-contractual template states is answered there, once — the EET reads it
    from services.eet.sfdr_items import mapping
    blocking = [b["field"] for b in comp["blocking"]]
    for _ in range(4):
        template = {n: mapping()["fields"][n]["article_8"] for n in blocking if n in mapping()["fields"]}
        items: dict = {}
        for rule in template.values():
            if rule["take"] == "values":
                items.setdefault(rule["item"], {"values": {}})["values"].update({lbl: 10 for lbl in rule["labels"]})
            else:
                items[rule["item"]] = {"ticked": True, **({"percent": 20} if rule["take"] == "percent" else {})}
        if items:
            r = c.put(f"/v1/funds/{c.fund}/sfdr-documents/precontractual/answers", headers=c.maker, json={"answers": items}).json()
            assert not r["refused"], r["refused"]
        org_vals = {n: _valid(fl[n]) for n in blocking if fl[n]["scope"] == "organisation"}
        fund_vals = {n: _valid(fl[n]) for n in blocking if fl[n]["scope"] == "fund" and n not in template}
        for body in ({"values": org_vals}, {"fund_id": c.fund, "values": fund_vals}):
            r = c.put("/v1/eet/answers", headers=c.maker, json=body).json()
            assert not r["refused"], r["refused"]
        after = c.get(f"/v1/eet/draft?uses={uses}", headers=c.maker).json()
        blocking = [b["field"] for b in after["completeness"]["blocking"]]
        if not blocking:
            break
    assert after["completeness"]["ready"], blocking
    template_field = "20180_Financial_Instrument_Products_Minimal_Proportion_Of_Sustainable_Investments_Art_8"
    assert after["rows"][0]["values"].get(template_field) in (None, "0.2")     # when asked for, read from the template
    assert after["rows"][0]["values"]["30020_GHG_Emissions_Scope_1_Value"] != "1"      # the book's figure, not the typed 1

    # prepare → the maker can't approve → the approver approves → published
    v1 = c.post("/v1/eet/versions", headers=c.maker, json={"uses": uses.split(","), "note": "first EET"})
    assert v1.status_code == 201, v1.text
    v1 = v1.json()
    assert v1["status"] == "pending" and v1["version"] == 1 and v1["n_share_classes"] == 2
    own = c.post(f"/v1/approvals/{v1['approval_request_id']}/decide", headers=c.maker, json={"decision": "approved"})
    assert own.status_code in (403, 422)
    ok = c.post(f"/v1/approvals/{v1['approval_request_id']}/decide", headers=c.checker, json={"decision": "approved", "reason": "checked"})
    assert ok.status_code == 200, ok.text
    pub = c.get(f"/v1/eet/versions/{v1['publication_id']}", headers=c.maker).json()
    assert pub["status"] == "published" and pub["hash_verified"]

    # the file: FinDatEx field order, one row per ISIN
    x = c.get(f"/v1/eet/versions/{v1['publication_id']}/export?format=csv", headers=c.maker)
    assert x.status_code == 200 and "EET_V1.1.3_v1" in x.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(x.content.decode()), delimiter=";"))
    assert rows[0][0] == "00010_EET_Version" and len(rows[0]) == 616 and len(rows) == 3
    rec = dict(zip(rows[0], rows[1]))
    assert rec["20000_Financial_Instrument_Identifying_Data"] == ISINS[0] and rec["00080_EET_Data_Reporting_SFDR_Entity_Level"] == "Y"
    xl = c.get(f"/v1/eet/versions/{v1['publication_id']}/export?format=xlsx", headers=c.maker)
    assert xl.status_code == 200 and xl.content[:2] == b"PK"

    # nothing changed → up to date; a new share class → a change to publish
    assert c.get("/v1/eet/changes", headers=c.maker).json()["up_to_date"]
    c.post(f"/v1/funds/{c.fund}/share-classes", headers=c.maker,
           json={"isin": ISINS[2], "name": "C GBP Acc", "currency": "GBP", "distribution": "accumulating"})
    ch = c.get("/v1/eet/changes", headers=c.maker).json()
    assert not ch["up_to_date"] and ch["added_share_classes"] == [ISINS[2]]

    # a held ISIN that is an own share class resolves to its fund
    rs = c.get(f"/v1/share-classes/resolve?isin={ISINS[1].lower()}", headers=c.maker).json()
    assert rs["valid"] and rs["share_class"]["fund_id"] == c.fund

    # the published version can't be changed or deleted
    with get_session() as s:
        for sql in ("UPDATE eet_publications SET payload = '{}'::jsonb WHERE publication_id = CAST(:p AS uuid)",
                    "UPDATE eet_publications SET status = 'rejected' WHERE publication_id = CAST(:p AS uuid)",
                    "DELETE FROM eet_publications WHERE publication_id = CAST(:p AS uuid)"):
            with pytest.raises(DBAPIError):
                s.execute(text(sql), {"p": v1["publication_id"]})
            s.rollback()


def test_a_fund_with_no_sovereign_or_property_holdings_is_not_asked_for_those_pais(am):
    c = am
    c.post(f"/v1/funds/{c.fund}/share-classes", headers=c.maker,
           json={"isin": ISINS[0], "name": "A EUR Acc", "currency": "EUR", "distribution": "accumulating"})
    d = c.get("/v1/eet/draft?uses=entity", headers=c.maker).json()
    v = d["rows"][0]["values"]
    assert v["31200_GHG_Intensity_Eligible_Assets"] == "0" and "31170_GHG_Intensity_Value" not in v
    assert not any(b["field"].startswith(("311", "312", "313")) for b in d["completeness"]["blocking"])
