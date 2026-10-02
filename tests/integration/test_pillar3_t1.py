"""Pillar 3 Template 1 columns i-k to the instructions (E103, E119-E121) and Template 5 cells traced to their exposures
(E105) — end to end through the HTTP API on the demo bank (Meridian), inside one rolled-back transaction.

The lifecycle: the loan tape names each exposure's counterparty → the counterparties file states each counterparty's total
liabilities ONCE → the institution states its method (switches) and its sector-average intensities (four eyes) → a filing
freezes the book and the statements → validation, form, annex and export. Every fact the figures read is stated here: the
demo book's emissions, counterparty ids and Template 1 statements are set aside first (E81/E85).
"""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import pytest
from sqlalchemy import text

from services.governance import pillar3_t1 as T1
from tests.integration.conftest import login as _login
from tests.integration.money_method import state_method
from tests.integration.test_intake_pipeline import BANK_ORG
from tests.integration.test_pillar3_report import _new_filing, _payload

pytestmark = pytest.mark.integration
ADMIN = ("admin@meridian.demo", "Demo!admin1")
CHECKER = ("approver@meridian.demo", "Demo!approve1")
CP_A, CP_C = "T1-CP-A", "T1-CP-C"
L = {CP_A: 2_000_000_000.0, CP_C: 500_000_000.0}
# exposure → (counterparty on the first loan tape, scopes 1-3 gathered, reported by the company, NACE code)
BOOK = {"e1": (CP_A, (100.0, 50.0, 1_000.0), True, "C24.10"),
        "e2": (CP_A, (100.0, 50.0, 1_000.0), True, "C24.10"),
        "e3": (CP_C, (40.0, 10.0, None), False, "C24.20"),       # no scope 3 gathered: the sector average stands in
        "e4": (None, (5.0, 5.0, 5.0), True, "A01.11")}           # no counterparty id on the first loan tape
INTENSITY = 300.0                                                # tCO2e per EUR million of total liabilities (stated)


def _findings(api, h, fid) -> dict:
    r = api.get(f"/v1/filings/{fid}/validation", headers=h)
    assert r.status_code == 200, r.text
    return {f["rule"]: f for f in r.json()["findings"]}


def _form(api, h, fid) -> tuple[dict, dict]:
    form = api.get(f"/v1/filings/{fid}/form", headers=h).json()
    return {d["key"]: d for g in form["groups"] for d in g["datapoints"]}, form


def _approve(api, checker, rid):
    r = api.post(f"/v1/approvals/{rid}/decide", headers=checker, json={"decision": "approved", "reason": "checked"})
    assert r.status_code == 200, r.text


def _switch(api, h, checker, **values):
    r = api.patch("/v1/calc-settings", headers=h, json={"interpretation": values})
    assert r.status_code == 200, r.text
    if r.json()["status"] == "pending_approval":
        _approve(api, checker, r.json()["request_id"])


def _file(api, h) -> str:
    """A new Pillar 3 filing on what is stated now (the method stays as this test stated it)."""
    api.s.execute(text("UPDATE regulatory_filing SET status = 'superseded' WHERE org_id = CAST(:o AS uuid) "
                       "AND framework = 'bank_p3esg' AND status NOT IN ('superseded', 'withdrawn')"), {"o": BANK_ORG})
    pf = api.get("/v1/filings/preflight?framework=bank_p3esg", headers=h).json()
    g = api.post("/v1/filings", headers=h, json={"framework": "bank_p3esg", "confirm_token": pf["confirm_token"]})
    assert g.status_code == 201, g.text
    return g.json()["filing_id"]


def _csv(header: list[str], rows: list[list]) -> bytes:
    return ("\n".join([",".join(header)] + [",".join("" if v is None else str(v) for v in r) for r in rows]) + "\n").encode()


def _land(api, h, checker, path, body: bytes, name: str):
    r = api.post(path, headers=h, files={"file": (name, body, "text/csv")},
                 data={"currency": "EUR", "book_date": "2025-12-31", "approval_reason": "E2E Template 1"})
    assert r.status_code in (200, 202), r.text[:800]
    if r.status_code == 202:                                     # a check asked for a second person
        _approve(api, checker, r.json()["approval_request_id"])
    return r.json()


def _loan_tape(api, h, checker, ids: dict, who: dict):
    """Re-send the chosen exposures on the loan tape exactly as held, with their counterparty id (borrower_entity_id)."""
    rows = []
    for key, cp in who.items():
        a = api.s.execute(text("""
            SELECT e.external_ref, e.entity_name, e.entity_type, CAST(e.latitude AS FLOAT) AS lat, CAST(e.longitude AS FLOAT) AS lon,
                   CAST(e.primary_value_eur AS FLOAT) AS v, e.sector, CAST(x.counterparty_evic_eur AS FLOAT) AS evic,
                   CAST(x.outstanding_loan_balance_eur AS FLOAT) AS ob, e.country
            FROM portfolio_entities e JOIN ext_banking x ON x.entity_id = e.entity_id WHERE e.entity_id = CAST(:e AS uuid)"""),
            {"e": ids[key]}).mappings().first()
        rows.append([a["external_ref"], a["entity_name"].replace(",", " "), a["entity_type"], a["lat"], a["lon"], a["v"],
                     (a["sector"] or "").replace(",", " "), a["evic"], a["ob"], a["country"], cp])
    body = _csv(["external_ref", "asset_name", "asset_type", "latitude", "longitude", "appraised_value_eur", "sector",
                 "counterparty_evic_eur", "outstanding_loan_balance_eur", "country", "borrower_entity_id"], rows)
    return _land(api, h, checker, "/v1/bank/assets/upload", body, "loan-tape.csv")


def _counterparties(api, h, checker, rows: list[list]):
    body = _csv(["counterparty_ref", "counterparty_name", "total_liabilities_eur", "currency", "book_date"], rows)
    return _land(api, h, checker, "/v1/bank/counterparties/upload", body, "counterparties.csv")


def _set_aside_and_state(api) -> dict:
    """The demo book's Template 1 facts and statements set aside; four exposures state theirs (emissions as gathered)."""
    s = api.s
    s.execute(text("""UPDATE ext_banking x SET ghg_emissions_scope1_tco2e = NULL, ghg_emissions_scope2_tco2e = NULL,
                      ghg_emissions_scope3_tco2e = NULL, emissions_company_reported = NULL
                      FROM portfolio_entities e WHERE e.entity_id = x.entity_id AND e.org_id = CAST(:o AS uuid)"""), {"o": BANK_ORG})
    s.execute(text("UPDATE portfolio_entities SET borrower_entity_id = NULL WHERE org_id = CAST(:o AS uuid)"), {"o": BANK_ORG})
    s.execute(text("DELETE FROM bank_counterparties WHERE org_id = CAST(:o AS uuid)"), {"o": BANK_ORG})
    s.execute(text("UPDATE org_calc_settings SET interpretation = interpretation - :a - :b - :c - :d WHERE org_id = CAST(:o AS uuid)"),
              {"a": T1.ESTIMATION, "b": T1.ATTRIBUTION, "c": T1.K_READING, "d": T1.S3_BASIS, "o": BANK_ORG})
    s.execute(text("DELETE FROM template_answers WHERE org_id = CAST(:o AS uuid) AND family = 'bank_p3esg' AND item_id LIKE 't1.%'"),
              {"o": BANK_ORG})
    from services.governance.filings import reporting_period_end
    state_method(s, BANK_ORG, reporting_period_end(s, BANK_ORG))      # the method the other templates read (no intensities)
    ids = [r[0] for r in s.execute(text("""
        SELECT e.entity_id::text FROM portfolio_entities e JOIN ext_banking x ON x.entity_id = e.entity_id
        WHERE e.org_id = CAST(:o AS uuid) AND e.vertical = 'banking' AND e.source = 'own' AND x.outstanding_loan_balance_eur > 0
          AND e.latitude IS NOT NULL ORDER BY e.entity_id LIMIT 4"""), {"o": BANK_ORG})]
    out = dict(zip(BOOK, ids))
    for key, eid in out.items():
        _, g, rep, nace = BOOK[key]
        s.execute(text("UPDATE portfolio_entities SET nace_code = :n, external_ref = :r WHERE entity_id = CAST(:e AS uuid)"),
                  {"n": nace, "r": f"T1-{key}", "e": eid})
        s.execute(text("""UPDATE ext_banking SET counterparty_sector = 'non_financial_corporation',
                          counterparty_evic_eur = COALESCE(counterparty_evic_eur, 1000000000),
                          ghg_emissions_scope1_tco2e = :g1, ghg_emissions_scope2_tco2e = :g2, ghg_emissions_scope3_tco2e = :g3,
                          emissions_company_reported = :rep WHERE entity_id = CAST(:e AS uuid)"""),
                  {"e": eid, "g1": g[0], "g2": g[1], "g3": g[2], "rep": rep})
    assert len(out) == 4
    return out


def test_the_switches_are_offered_with_their_quotes_and_refuse_anything_else(api):
    h = _login(api, *ADMIN)
    cat = {c["key"]: c for c in api.get("/v1/calc-settings/catalog", headers=h).json()["interpretation"]}
    assert cat[T1.ATTRIBUTION]["default"] is None and cat[T1.ATTRIBUTION]["allowed"] == ["exposure_over_total_liabilities"]
    assert "total liabilities (accounting liabilities and shareholders’ equity)" in cat[T1.ATTRIBUTION]["description"]
    assert cat[T1.ESTIMATION]["allowed"] == ["scope_1_2_3", "scope_1_2", "not_yet_estimating"]
    assert cat[T1.K_READING]["default"] is None and cat[T1.K_READING]["allowed"] == ["scopes_estimated", "all_three_scopes"]
    assert "scope 1, 2 and 3 emissions" in cat[T1.K_READING]["description"]
    assert cat[T1.S3_BASIS]["default"] is None and "sector-average emissions intensity" in cat[T1.S3_BASIS]["description"]
    for key, bad in ((T1.ATTRIBUTION, "pcaf"), (T1.S3_BASIS, "revenue")):
        assert api.patch("/v1/calc-settings", headers=h, json={"interpretation": {key: bad}}).status_code == 422


def test_template_1_end_to_end_one_counterparty_one_figure(api):
    h, checker = _login(api, *ADMIN), _login(api, *CHECKER)
    s = api.s
    ids = _set_aside_and_state(api)
    frozen_of = lambda p: {a["asset_id"]: a for a in p["assets"]}              # noqa: E731

    # ── 1 the loan tape names each exposure's counterparty; the counterparties file states each one's figure once ──
    _loan_tape(api, h, checker, ids, {k: BOOK[k][0] for k in ("e1", "e2", "e3")})
    assert s.execute(text("SELECT count(*) FROM portfolio_entities WHERE org_id = CAST(:o AS uuid) AND borrower_entity_id = :c"),
                     {"o": BANK_ORG, "c": CP_A}).scalar() == 2
    bad = api.post("/v1/bank/counterparties/validate", headers=h, data={"currency": "EUR", "book_date": "2025-12-31"},
                   files={"file": ("cp.csv", _csv(["counterparty_ref", "total_liabilities_eur", "currency"],
                                                  [[CP_A, 2_000_000_000, "EUR"]]), "text/csv")})
    assert "balance sheet" in bad.text, bad.text[:600]                        # the figure needs its balance-sheet date
    _counterparties(api, h, checker, [[CP_A, "Alpha AG", L[CP_A], "EUR", "2025-12-31"], [CP_C, "Cobalt SA", L[CP_C], "EUR", "2025-09-30"]])
    cps = {c["counterparty_ref"]: c for c in api.get("/v1/bank/counterparties", headers=h).json()["counterparties"]}
    assert cps[CP_A]["n_exposures"] == 2 and cps[CP_A]["total_liabilities_eur"] == L[CP_A]
    assert cps[CP_C]["total_liabilities_date"] == "2025-09-30"

    # ── 2 the institution states scopes 1-3 and the attribution, and authors the narrative ──
    _switch(api, h, checker, **{T1.ESTIMATION: "scope_1_2_3", T1.ATTRIBUTION: "exposure_over_total_liabilities"})
    body = {"values": {n["key"]: f"Our {n['key']}" for n in T1.required_narrative("scope_1_2_3")}}
    assert api.patch("/v1/filings/qualitative/p3esg", headers=h, json=body).status_code == 200
    fid = _file(api, h)
    p = _payload(s, fid)
    fr = frozen_of(p)
    assert fr[ids["e1"]]["counterparty_total_liabilities_eur"] == fr[ids["e2"]]["counterparty_total_liabilities_eur"] == L[CP_A]
    f = _findings(api, h, fid)
    assert not f["t1_counterparty_identified"]["passed"]                      # e4: emissions, no counterparty id
    assert not f["t1_scope3_basis"]["passed"] and "not stated: how sector-average intensity is used" in f["t1_scope3_basis"]["message"]
    assert f["t1_counterparty_figure_agreed"]["passed"] and f["t1_total_liabilities_stated"]["passed"]

    # ── 3 a conflict the migration left (two exposures stated different figures) blocks until the one figure is stated ──
    s.execute(text("""UPDATE bank_counterparties SET total_liabilities_eur = NULL, total_liabilities_date = NULL, money_source = NULL,
                      liabilities_conflict = CAST(:c AS jsonb) WHERE org_id = CAST(:o AS uuid) AND counterparty_ref = :r"""),
              {"o": BANK_ORG, "r": CP_C, "c": json.dumps([{"entity_id": ids["e3"], "eur": 1, "date": "2025-01-01", "source": None},
                                                          {"entity_id": ids["e4"], "eur": 2, "date": "2025-01-01", "source": None}])})
    cps = {c["counterparty_ref"]: c for c in api.get("/v1/bank/counterparties", headers=h).json()["counterparties"]}
    assert cps[CP_C]["total_liabilities_eur"] is None and len(cps[CP_C]["liabilities_conflict"]) == 2
    f = _findings(api, h, _file(api, h))
    assert not f["t1_counterparty_figure_agreed"]["passed"] and f["t1_counterparty_figure_agreed"]["severity"] == "blocking"
    _counterparties(api, h, checker, [[CP_C, "Cobalt SA", L[CP_C], "EUR", "2025-09-30"]])
    assert s.execute(text("SELECT liabilities_conflict FROM bank_counterparties WHERE org_id = CAST(:o AS uuid) AND counterparty_ref = :r"),
                     {"o": BANK_ORG, "r": CP_C}).scalar() is None

    # ── 4 e4 gets its counterparty on the loan tape; the sector-average source is stated and attested (four eyes) ──
    _loan_tape(api, h, checker, ids, {"e4": CP_A})
    _switch(api, h, checker, **{T1.S3_BASIS: "intensity_x_total_liabilities"})
    from services.governance.filings import reporting_period_end
    pe = reporting_period_end(s, BANK_ORG).isoformat()
    post = {"framework": "method", "datapoint_key": T1.INTENSITY, "value_num": INTENSITY, "reporting_period_end": pe,
            "breakdown_member": "C24"}
    r = api.post("/v1/provided", headers=h, json=post)
    assert r.status_code == 400 and "source" in r.text                         # a published figure names its source
    r = api.post("/v1/provided", headers=h, json={**post, "provider_name": "Source X sector averages", "data_vintage": "2024-12-31"})
    assert r.status_code == 201, r.text
    _approve(api, checker, r.json()["approval_request_id"])
    fid = _file(api, h)
    p = _payload(s, fid)
    fr, rec = frozen_of(p), p[T1.RECORD]
    assert rec["sector_intensity"]["C24"]["value"] == INTENSITY and rec["sector_intensity"]["C24"]["provider"].startswith("Source X")
    f = _findings(api, h, fid)
    assert all(f[k]["passed"] for k in ("t1_method_stated", "t1_counterparty_identified", "t1_counterparty_figure_agreed",
                                        "t1_scope3_basis", "t1_total_liabilities_stated", "t1_exposure_within_liabilities",
                                        "t1_emissions_source_recorded", "t1_k_reading_stated", "t1_narrative_authored")), f

    # the figures, by hand from the frozen book: x / L × scopes; e3's scope 3 = intensity × L / 1 000 000
    def x(k):
        return fr[ids[k]]["outstanding_loan_balance_eur"]
    s3_e3 = INTENSITY * L[CP_C] / 1_000_000
    want_i = sum(x(k) / L[CP_A] * sum(BOOK[k][1]) for k in ("e1", "e2", "e4")) + x("e3") / L[CP_C] * (40 + 10 + s3_e3)
    want_j = sum(x(k) / L[CP_A] * BOOK[k][1][2] for k in ("e1", "e2", "e4")) + x("e3") / L[CP_C] * s3_e3
    dps, form = _form(api, h, fid)
    assert dps["emissions.total"]["value"] == pytest.approx(want_i, rel=1e-9)
    assert dps["emissions.scope3"]["value"] == pytest.approx(want_j, rel=1e-9)
    from services.governance.filing_annex import _p3_spec
    from services.governance.pillar3_grids import BINDING, build
    total = next(rid for rid, how in BINDING["T1"]["rows"].items() if how == "computed:total")
    gross = next(r for r in build(_p3_spec(p), "T1", p["assets"], t1=rec)["rows"] if r["id"] == total)["values"]["a"]
    assert dps["emissions.company_reported_pct"]["value"] == round((x("e1") + x("e2") + x("e4")) / gross * 100, 1)  # e3 is not
    t1 = next(sec for sec in form["annex"]["sections"] if sec.get("key") == "t1")
    assert "sector-average" in t1["note"] and "Source X" in t1["note"] and "Scope 3 phase-in on" in t1["note"]

    # the export carries the counterparty and the frozen statements
    js = api.get(f"/v1/filings/{fid}/export", headers=h, params={"format": "json"})
    assert js.status_code == 200 and json.loads(js.content)["payload"][T1.RECORD]["sector_intensity"]["C24"]["value"] == INTENSITY
    xl = api.get(f"/v1/filings/{fid}/export", headers=h, params={"format": "xlsx"})
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(xl.content), read_only=True)
    cells = {str(c) for ws in wb.worksheets for row in ws.iter_rows(values_only=True) for c in row if c is not None}
    assert "counterparty_ref" in cells and CP_A in cells

    # ── 5 scopes 1 and 2: j blank; k needs the institution's reading of 'scope 1, 2 and 3' ──
    _switch(api, h, checker, **{T1.ESTIMATION: "scope_1_2"})
    api.patch("/v1/filings/qualitative/p3esg", headers=h, json={"values": {"t1.plans_scope3": "From 2027"}})
    fid = _file(api, h)
    dps, _ = _form(api, h, fid)
    assert dps["emissions.scope3"]["value"] is None and dps["emissions.company_reported_pct"]["value"] is None
    assert T1.K_READING in dps["emissions.company_reported_pct"]["note"]
    assert not _findings(api, h, fid)["t1_k_reading_stated"]["passed"]
    _switch(api, h, checker, **{T1.K_READING: "scopes_estimated"})
    dps, _ = _form(api, h, _file(api, h))
    assert dps["emissions.company_reported_pct"]["value"] == round((x("e1") + x("e2") + x("e4")) / gross * 100, 1)
    _switch(api, h, checker, **{T1.K_READING: "all_three_scopes"})
    dps, _ = _form(api, h, _file(api, h))
    assert dps["emissions.company_reported_pct"]["value"] == 0.0

    # ── 6 not yet estimating: i and j blank, k is 0 % ──
    _switch(api, h, checker, **{T1.ESTIMATION: "not_yet_estimating"})
    api.patch("/v1/filings/qualitative/p3esg", headers=h, json={"values": {"t1.plans_emissions": "From 2027"}})
    fid = _file(api, h)
    dps, _ = _form(api, h, fid)
    assert (dps["emissions.total"]["value"], dps["emissions.scope3"]["value"], dps["emissions.company_reported_pct"]["value"]) == (None, None, 0.0)
    assert _findings(api, h, fid)["t1_narrative_authored"]["passed"]


def test_the_phase_in_shows_divisions_not_yet_phased_in_on_the_reference_date(api):
    """A filing for the year ending 31 December 2023: the A01 exposure (Article 5(1)(c), from 23 December 2024) is in its
    phase-in period; C24 (point (b), from 23 December 2022) is phased in."""
    h, checker = _login(api, *ADMIN), _login(api, *CHECKER)
    ids = _set_aside_and_state(api)
    _loan_tape(api, h, checker, ids, {"e1": CP_A, "e4": CP_A})
    _counterparties(api, h, checker, [[CP_A, "Alpha AG", L[CP_A], "EUR", "2023-12-31"]])
    r = api.patch("/v1/filings/reporting-basis", headers=h, json={"reporting_period_end": "2023-12-31"})
    assert r.status_code == 200, r.text
    if r.json()["status"] == "pending_approval":
        _approve(api, checker, r.json()["request_id"])
    state_method(api.s, BANK_ORG, "2023-12-31")
    _switch(api, h, checker, **{T1.ESTIMATION: "scope_1_2_3", T1.ATTRIBUTION: "exposure_over_total_liabilities"})
    fid = _file(api, h)
    rec = _payload(api.s, fid)[T1.RECORD]
    assert rec["reference_date"] == "2023-12-31"
    _, form = _form(api, h, fid)
    note = next(sec for sec in form["annex"]["sections"] if sec.get("key") == "t1")["note"]
    pending = note.split("In their phase-in period")[1].split(")." )[0]
    assert "Scope 3 phase-in on 2023-12-31" in note and "A01 (point (c), from 2024-12-23;" in pending
    assert "C24" not in pending                                           # point (b): phased in from 23 December 2022


def test_the_migration_moves_one_figure_per_counterparty_and_keeps_a_conflict(session_rolled_back):
    """The migration's own move (p3_t1_counterparty_20261002.MOVE_SQL), run on rows of the shape it migrates (temporary
    tables shadow the real ones inside this transaction): agreeing exposures give their counterparty one figure with its
    source; disagreeing ones leave no figure and the statements that disagree."""
    s = session_rolled_back
    path = Path(__file__).resolve().parents[2] / "core/db/migrations/versions/p3_t1_counterparty_20261002.py"
    spec = importlib.util.spec_from_file_location("p3_t1_counterparty_mig", path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    s.execute(text("""
        CREATE TEMP TABLE portfolio_entities (entity_id uuid, org_id uuid, borrower_entity_id varchar(20)) ON COMMIT DROP;
        CREATE TEMP TABLE ext_banking (entity_id uuid, counterparty_total_liabilities_eur numeric(20,2),
                                       counterparty_total_liabilities_date date, counterparty_issuer_id uuid, money_source jsonb) ON COMMIT DROP;
        CREATE TEMP TABLE bank_counterparties (LIKE public.bank_counterparties INCLUDING DEFAULTS) ON COMMIT DROP;
    """))
    o = BANK_ORG
    ent = {"agree1": ("A", 420e6, "2025-12-31", {"amount": 400e6, "currency": "USD"}),
           "agree2": ("A", 420e6, "2025-12-31", {"amount": 400e6, "currency": "USD"}),
           "agree3": ("A", None, None, None),                                          # states nothing: no disagreement
           "diff1": ("B", 100e6, "2025-12-31", None), "diff2": ("B", 120e6, "2025-12-31", None)}
    uid = {k: f"00000000-0000-4000-8000-0000000000{i:02d}" for i, k in enumerate(ent, 1)}
    for k, (ref, eur, d, src) in ent.items():
        s.execute(text("INSERT INTO portfolio_entities VALUES (CAST(:e AS uuid), CAST(:o AS uuid), :r)"), {"e": uid[k], "o": o, "r": ref})
        ms = json.dumps({"fields": {"counterparty_total_liabilities_eur": {**src, "eur": eur}}}) if src else None
        s.execute(text("INSERT INTO ext_banking VALUES (CAST(:e AS uuid), :v, CAST(:d AS date), NULL, CAST(:ms AS jsonb))"),
                  {"e": uid[k], "v": eur, "d": d, "ms": ms})
    s.execute(text(mig.MOVE_SQL))
    got = {r["counterparty_ref"]: r for r in s.execute(text(
        "SELECT counterparty_ref, CAST(total_liabilities_eur AS FLOAT) AS v, total_liabilities_date AS d, money_source, "
        "liabilities_conflict FROM pg_temp.bank_counterparties")).mappings()}
    assert got["A"]["v"] == 420e6 and str(got["A"]["d"]) == "2025-12-31" and got["A"]["liabilities_conflict"] is None
    assert got["A"]["money_source"]["fields"]["total_liabilities_eur"]["currency"] == "USD"
    assert got["B"]["v"] is None and {c["eur"] for c in got["B"]["liabilities_conflict"]} == {100e6, 120e6}
    s.execute(text("DROP TABLE pg_temp.bank_counterparties, pg_temp.ext_banking, pg_temp.portfolio_entities"))


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
