"""End to end, through the HTTP API: a Pillar 3 filing built to its specification, from the loan tape to the export.

  loan-tape facts (attributes upload) → qualitative authoring (unknown rows refused) → pre-flight → generate (freeze,
  with the governing spec) → the form: Template 7 placed by the stated facts, Template 10 offering its cells for entry →
  a Template 10 cell supplied for the filing's period → a second person attests it → the draft is refreshed → the value
  is frozen on the form → XLSX / JSON / XBRL exports.

The API runs with its database session replaced by one rolled-back transaction (commits are flushes), so the whole
lifecycle — including the append-only snapshot and engine-run records — leaves nothing behind.
"""
from __future__ import annotations

import csv
import io
import json
import zipfile

import pytest
from sqlalchemy import text

from tests.integration.conftest import login as _login
from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration


def _csv(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode()


def test_pillar3_from_the_loan_tape_to_the_export(api):
    maker = _login(api, "admin@meridian.demo", "Demo!admin1")
    checker = _login(api, "approver@meridian.demo", "Demo!approve1")
    s = api.s

    # 1 · the loan tape states the new facts for two exposures (attributes upload, matched by asset name)
    names = s.execute(text("""SELECT e.entity_name FROM portfolio_entities e JOIN ext_banking x ON x.entity_id = e.entity_id
                              WHERE e.org_id = CAST(:o AS uuid) AND e.vertical = 'banking' AND e.source = 'own'
                              GROUP BY e.entity_name HAVING count(*) = 1 ORDER BY e.entity_name LIMIT 2"""),
                      {"o": BANK_ORG}).scalars().all()
    rows = [{"asset_name": names[0], "counterparty_sector": "credit_institution", "instrument_type": "debt_securities",
             "nfrd_subject": "", "taxonomy_objective": "ccm", "ccm_sustainable": "true", "specialised_lending": "false"},
            {"asset_name": names[1], "counterparty_sector": "non_financial_corporation", "instrument_type": "equity_instruments",
             "nfrd_subject": "true", "taxonomy_objective": "cca", "ccm_sustainable": "false", "specialised_lending": ""}]
    r = api.post("/v1/bank/assets/attributes/upload", headers=maker, files={"file": ("facts.csv", _csv(rows), "text/csv")})
    assert r.status_code == 200 and r.json()["n_updated"] == 2, r.text
    stored = s.execute(text("""SELECT x.counterparty_sector, x.instrument_type, x.taxonomy_objective, x.ccm_sustainable
                               FROM ext_banking x JOIN portfolio_entities e ON e.entity_id = x.entity_id
                               WHERE e.entity_name = :n AND e.org_id = CAST(:o AS uuid)"""), {"n": names[0], "o": BANK_ORG}).one()
    assert tuple(stored) == ("credit_institution", "debt_securities", "ccm", True)

    # 2 · qualitative authoring: a row the governing tables do not have is refused; a printed sub-row is accepted
    assert api.patch("/v1/filings/qualitative/p3esg", headers=maker, json={"values": {"table9.z": "x"}}).status_code == 422
    r = api.patch("/v1/filings/qualitative/p3esg", headers=maker, json={"values": {"table2.d_i": "Community engagement policy."}})
    assert r.status_code == 200
    rows_ = {x["key"]: x["value"] for t in r.json()["tables"] for x in t["rows"]}
    assert rows_["table2.d_i"] == "Community engagement policy."

    # 3 · pre-flight and generate: the draft freezes the governing specification
    s.execute(text("UPDATE regulatory_filing SET status = 'superseded' WHERE org_id = CAST(:o AS uuid) AND framework = 'bank_p3esg' "
              "AND status NOT IN ('superseded', 'withdrawn')"),
              {"o": BANK_ORG})
    pf = api.get("/v1/filings/preflight?framework=bank_p3esg", headers=maker).json()
    g = api.post("/v1/filings", headers=maker, json={"framework": "bank_p3esg", "confirm_token": pf["confirm_token"]})
    assert g.status_code == 201, g.text
    fid = g.json()["filing_id"]
    form = api.get(f"/v1/filings/{fid}/form", headers=maker).json()
    assert form["period_end"] and "2024/3172" in form["annex"]["legal_basis"]
    sec = {x.get("key"): x for x in form["annex"]["sections"]}
    t7_row = {r["cells"][0]["text"].split(" · ")[0]: r for r in sec["t7"]["rows"] if r["type"] == "row"}
    assert t7_row["32"]["cells"][1]["text"] not in ("—", "")               # GAR assets placed from the stated facts
    t10_cells = [c for r in sec["t10"]["rows"] if r["type"] == "row" for c in r["cells"] if c.get("supply")]
    assert len(t10_cells) == 11 * 4                                        # 11 printed rows × columns c-f to enter

    # qualitative Tables 1-3: the text answered for this institution and reference date is frozen and printed; an
    # unanswered row blocks the filing until it is answered and the draft refreshed
    tab2 = {r["cells"][0]["text"].split(" ")[0]: r["cells"][1]["text"] for r in sec["p3_tab2"]["rows"] if r["type"] == "row"}
    assert tab2["(d)(i)"] == "Community engagement policy."
    v = api.get(f"/v1/filings/{fid}/validation", headers=maker).json()
    q = next(f for f in v["findings"] if f["rule"] == "qualitative_tables_answered")
    assert q["severity"] == "blocking" and not q["passed"]
    qual = api.get(f"/v1/filings/qualitative/p3esg?period_end={form['period_end']}", headers=maker).json()
    keys = [x["key"] for t in qual["tables"] if t["table"].startswith("TAB") for x in t["rows"]]
    assert api.patch("/v1/filings/qualitative/p3esg", headers=maker,
                     json={"values": {k: f"Answer {k}" for k in keys}, "period_end": form["period_end"]}).status_code == 200
    assert api.post(f"/v1/filings/{fid}/refresh", headers=maker).status_code == 200
    v = api.get(f"/v1/filings/{fid}/validation", headers=maker).json()
    assert next(f for f in v["findings"] if f["rule"] == "qualitative_tables_answered")["passed"]

    # 4 · supply a Template 10 cell for the filing's period; a second person attests it
    r = api.post("/v1/provided", headers=maker, json={"framework": "bank_p3esg", "datapoint_key": "T10.1.c",
                                                      "value_num": 12500000, "reporting_period_end": form["period_end"]})
    assert r.status_code == 201, r.text
    assert api.post("/v1/provided", headers=maker, json={"framework": "bank_p3esg", "datapoint_key": "T7.4.a", "value_num": 1,
                                                         "reporting_period_end": form["period_end"]}).status_code == 400
    assert api.post(f"/v1/approvals/{r.json()['approval_request_id']}/decide", headers=maker,
                    json={"decision": "approved"}).status_code == 422                 # the maker cannot attest their own (4-eyes)
    d = api.post(f"/v1/approvals/{r.json()['approval_request_id']}/decide", headers=checker, json={"decision": "approved"})
    assert d.status_code == 200, d.text

    # 5 · refresh the draft: the attested value is frozen into the filing and shown in its cell
    assert api.post(f"/v1/filings/{fid}/refresh", headers=maker).status_code == 200
    form = api.get(f"/v1/filings/{fid}/form", headers=maker).json()
    t10 = next(x for x in form["annex"]["sections"] if x.get("key") == "t10")
    cell = next(c for r in t10["rows"] if r["type"] == "row" for c in r["cells"] if c.get("key") == "T10.1.c")
    assert "12.5m" in cell["text"]

    # 6 · exports carry the templates and the supplied value
    js = json.loads(api.get(f"/v1/filings/{fid}/export?format=json", headers=maker).content)
    frozen = {p["key"]: p["value"] for p in js.get("payload", js).get("_provided_attested", [])} if isinstance(js, dict) else {}
    assert frozen.get("provided.T10.1.c") == 12500000
    xl = api.get(f"/v1/filings/{fid}/export?format=xlsx", headers=maker)
    assert xl.status_code == 200
    with zipfile.ZipFile(io.BytesIO(xl.content)) as z:
        sheets = " ".join(z.read(n).decode("utf-8", "ignore") for n in z.namelist() if n.startswith("xl/"))
    # the supplied cell as the template block writes it (the per-exposure sheet once held a demo asset value that contained
    # the digits by coincidence, E97)
    assert "Template 7" in sheets and "Template 10" in sheets and "12.5m" in sheets
    xb = api.get(f"/v1/filings/{fid}/export?format=xbrl", headers=maker)     # no XBRL until the EBA taxonomy is bound (E104)
    assert xb.status_code == 409 and "not an available format" in xb.text


def test_preparing_an_obligation_files_its_own_entity_and_period(api):
    """Prepare on an obligation's card files that obligation: its legal entity, its period — never the whole
    organisation or a different period (found in the 2026-09-29 walkthrough: the card passed only the framework)."""
    maker = _login(api, "admin@meridian.demo", "Demo!admin1")
    s = api.s
    obs = {(o["entity_name"], o["period_end"]): o for o in
           api.get("/v1/obligations", headers=maker).json()["obligations"] if o["framework"] == "bank_p3esg"}
    solo = obs[("Meridian Bank AG", "2025-12-31")]
    later = next(o for (_, pe), o in obs.items() if pe != "2025-12-31")
    other = next(o for (n, pe), o in obs.items() if n and n != "Meridian Bank AG" and pe == "2025-12-31")

    def token(entity_id=None):
        q = f"&entity_id={entity_id}" if entity_id else ""
        return api.get(f"/v1/filings/preflight?framework=bank_p3esg{q}", headers=maker).json()["confirm_token"]

    r = api.post("/v1/filings", headers=maker, json={"framework": "bank_p3esg", "confirm_token": token(),
                                                     "obligation_id": later["obligation_id"]})
    assert r.status_code == 409 and "change the reporting period" in r.json()["error"]["message"]
    r = api.post("/v1/filings", headers=maker, json={"framework": "bank_p3esg", "confirm_token": token(),
                                                     "obligation_id": solo["obligation_id"], "entity_id": other["entity_id"]})
    assert r.status_code == 409 and "not the obligation's entity" in r.json()["error"]["message"]

    # the pre-filing check is for the scope being filed: its figures are the entity's own book, and a confirmation
    # of the whole organisation cannot freeze the entity's filing
    whole = api.get("/v1/filings/preflight?framework=bank_p3esg", headers=maker).json()
    mine = api.get(f"/v1/filings/preflight?framework=bank_p3esg&entity_id={solo['entity_id']}", headers=maker).json()
    assert 0 < mine["total_value_eur"] < whole["total_value_eur"]
    r = api.post("/v1/filings", headers=maker, json={"framework": "bank_p3esg", "confirm_token": whole["confirm_token"],
                                                     "obligation_id": solo["obligation_id"]})
    assert r.status_code == 409 and "another scope" in r.json()["error"]["message"]
    r = api.post("/v1/filings", headers=maker, json={"framework": "bank_p3esg", "confirm_token": mine["confirm_token"],
                                                     "obligation_id": solo["obligation_id"]})
    assert r.status_code == 201, r.text
    row = s.execute(text("SELECT entity_id::text, period_end::text FROM regulatory_filing WHERE filing_id = CAST(:f AS uuid)"),
                    {"f": r.json()["filing_id"]}).one()
    assert tuple(row) == (solo["entity_id"], "2025-12-31")
    q = s.execute(text("""SELECT s.payload -> 'qualitative' FROM regulatory_filing f JOIN report_snapshots s
                           ON s.snapshot_id = f.snapshot_id WHERE f.filing_id = CAST(:f AS uuid)"""), {"f": r.json()["filing_id"]}).scalar()
    assert q["entity_id"] == solo["entity_id"] and q["reference_date"] == "2025-12-31"   # the entity's own text, not the org's
    card = next(o for o in api.get("/v1/obligations", headers=maker).json()["obligations"]
                if o["obligation_id"] == solo["obligation_id"])
    assert card["filing_id"] == r.json()["filing_id"]                        # the card now links to its filing


def test_bank_taxonomy_filing_is_built_to_the_governing_version_and_takes_entered_cells(api):
    """EU Taxonomy Art. 8 end to end: a bank TCFD filing is frozen with the governing bank_taxonomy version and the
    loan tape's facts; its form renders every Annex VI template of that version (exposures placed, KPIs computed);
    a cell the institution enters (financial guarantees, CapEx-based) is supplied, attested by a second person, and
    appears on the refreshed draft."""
    maker = _login(api, "admin@meridian.demo", "Demo!admin1")
    checker = _login(api, "approver@meridian.demo", "Demo!approve1")
    s = api.s
    s.execute(text("UPDATE regulatory_filing SET status = 'superseded' WHERE org_id = CAST(:o AS uuid) AND framework = 'bank_tcfd' "
                   "AND status NOT IN ('superseded', 'withdrawn')"), {"o": BANK_ORG})
    pf = api.get("/v1/filings/preflight?framework=bank_tcfd", headers=maker).json()
    g = api.post("/v1/filings", headers=maker, json={"framework": "bank_tcfd", "confirm_token": pf["confirm_token"]})
    assert g.status_code == 201, g.text
    fid = g.json()["filing_id"]
    frozen = s.execute(text("""SELECT s.payload -> '_specs' -> 'bank_taxonomy' FROM regulatory_filing f
                               JOIN report_snapshots s ON s.snapshot_id = f.snapshot_id WHERE f.filing_id = CAST(:f AS uuid)"""),
                       {"f": fid}).scalar()
    import services.regspec as R
    governing = R.governing("bank_taxonomy", period_end=pf["basis"]["reporting_period_end"][:10])
    assert frozen["version"] == governing["version"] and frozen["disclosed_on"]
    form = api.get(f"/v1/filings/{fid}/form", headers=maker).json()
    tx = [x for x in form["annex"]["sections"] if (x.get("spec") or {}).get("framework") == "bank_taxonomy"]
    assert {x["spec"]["template"] for x in tx} == {t["id"] for t in governing["templates"]}
    assert "could not be placed" not in " ".join(x["note"] for x in tx)          # the loan tape places every exposure
    t1c = next(x for x in tx if x["key"] == "taxonomy_t1_capex")
    cell = next(c for r in t1c["rows"] if r["type"] == "row" for c in r["cells"] if c.get("supply"))
    r = api.post("/v1/provided", headers=maker, json={"framework": "bank_tcfd", "datapoint_key": cell["key"],
                                                      "value_num": 7_500_000, "reporting_period_end": form["period_end"]})
    assert r.status_code == 201, r.text
    assert api.post(f"/v1/approvals/{r.json()['approval_request_id']}/decide", headers=checker,
                    json={"decision": "approved"}).status_code == 200
    assert api.post(f"/v1/filings/{fid}/refresh", headers=maker).status_code == 200
    form = api.get(f"/v1/filings/{fid}/form", headers=maker).json()
    t1c = next(x for x in form["annex"]["sections"] if x.get("key") == "taxonomy_t1_capex")
    shown = next(c for r in t1c["rows"] if r["type"] == "row" for c in r["cells"] if c.get("key") == cell["key"])
    assert shown["text"] != "—"
    assert api.post("/v1/provided", headers=maker, json={"framework": "bank_tcfd", "datapoint_key": "T1.4.b",
                                                         "value_num": 1, "reporting_period_end": form["period_end"]}).status_code == 400


def test_reit_taxonomy_filing_builds_annex_ii_from_the_property_book_and_takes_ledger_cells(api):
    """EU Taxonomy Art. 8 for a building owner, end to end: the filing freezes the governing nonfin_taxonomy version and
    the property book; the form renders every Annex II template of that version with the buildings placed in A.1 / A.2
    by the 7.7 criteria; a CapEx figure from the undertaking's ledger is supplied, attested by a second person, and
    appears on the refreshed draft; a computed turnover cell is refused."""
    stellar = "33333333-3333-4333-8333-333333333333"
    maker = _login(api, "admin@stellar.demo", "Demo!admin1")
    checker = _login(api, "approver@stellar.demo", "Demo!approve1")
    s = api.s
    s.execute(text("UPDATE regulatory_filing SET status = 'superseded' WHERE org_id = CAST(:o AS uuid) AND framework = 'reit_taxonomy' "
                   "AND status NOT IN ('superseded', 'withdrawn')"), {"o": stellar})
    pf = api.get("/v1/filings/preflight?framework=reit_taxonomy", headers=maker).json()
    g = api.post("/v1/filings", headers=maker, json={"framework": "reit_taxonomy", "confirm_token": pf["confirm_token"]})
    assert g.status_code == 201, g.text
    fid = g.json()["filing_id"]
    import services.regspec as R
    governing = R.governing("nonfin_taxonomy", period_end=pf["basis"]["reporting_period_end"][:10])
    form = api.get(f"/v1/filings/{fid}/form", headers=maker).json()
    tx = [x for x in form["annex"]["sections"] if (x.get("spec") or {}).get("framework") == "nonfin_taxonomy"]
    assert {x["spec"]["template"] for x in tx} == {t["id"] for t in governing["templates"]}
    summary_rows = next(x for x in tx if x["spec"]["template"] == "T1")["rows"]
    turnover = next(r for r in summary_rows if r["type"] == "row" and r["cells"][0]["text"].startswith("r1"))
    assert all(c["text"] != "—" for c in turnover["cells"][1:6])                 # KPI: total, eligible %, aligned
    capex = next(c for r in summary_rows if r["type"] == "row" for c in r["cells"] if c.get("supply"))
    r = api.post("/v1/provided", headers=maker, json={"framework": "reit_taxonomy", "datapoint_key": capex["key"],
                                                      "value_num": 4_200_000, "reporting_period_end": form["period_end"]})
    assert r.status_code == 201, r.text
    assert api.post(f"/v1/approvals/{r.json()['approval_request_id']}/decide", headers=checker,
                    json={"decision": "approved"}).status_code == 200
    assert api.post(f"/v1/filings/{fid}/refresh", headers=maker).status_code == 200
    form = api.get(f"/v1/filings/{fid}/form", headers=maker).json()
    t1 = next(x for x in form["annex"]["sections"] if x.get("key") == "taxonomy_t1")
    assert next(c for r in t1["rows"] if r["type"] == "row" for c in r["cells"] if c.get("key") == capex["key"])["text"] != "—"
    assert api.post("/v1/provided", headers=maker, json={"framework": "reit_taxonomy", "datapoint_key": "T1.r1.2",
                                                         "value_num": 1, "reporting_period_end": form["period_end"]}).status_code == 400
