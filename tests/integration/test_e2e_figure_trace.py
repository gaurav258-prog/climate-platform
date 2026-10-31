"""End to end, through the HTTP API: one filed figure traced as a graph (services.governance.figure_trace) — the law and
the specification, the cell, its calculation and the attested statements it rests on, the book, what the run read — on
Iberia Mutual's Solvency II nat-cat reports, read only from what each filing froze.

  solo     Iberia Mutual Seguros' S.27.01.01: a region's exposure cell → the instruction naming it (quoted, found word
           for word in the stored ITS) → the formula line → the policies the formula placed there, tying to the printed
           exposure and count → the run that read the book; the after-mitigation cell rests on the attested treaty
  group    Iberia Mutual Group's S.27.01.04 under a combination of methods: every method statement with who attested
           it; Seguros in, Iberia Re left out (method 2) with its policies counted, none of them in the cell
  capped   a book larger than the cap shows a 'more' node; expanding it shows more
  refused  a greyed cell, a cell the template does not print, another template's cell
  premium  an other-region premium cell is the filer's statement (or that it is missing), never the book's
  Pillar 3 a Template 5 cell → its column's instructions → the at-risk threshold → its exposures, their scores and
           feeds, every column tying; a half-year report (E354) traces on the half-year it froze

Every test runs in one rolled-back transaction: nothing is left behind.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.integration.money_method import state_method
from tests.integration.test_e2e_s2701 import (
    GROUP,
    IBERIA,
    IBERIA_RE,
    SEGUROS,
    _generate,
    _state,
    _users,
)
from tests.integration.test_e2e_s2704_group import _method

pytestmark = pytest.mark.integration
TREATY = {"ri_quota_share_pct": 50, "ri_xol_attachment_eur": 5_000_000, "ri_xol_limit_eur": 50_000_000}


def _trace(api, h, fid: str, cell: str, **params) -> dict:
    r = api.get(f"/v1/filings/{fid}/trace", headers=h, params={"cell": cell, **params})
    assert r.status_code == 200, r.text
    return r.json()


def _peril(d: dict) -> str:
    return next(n for n in d["nodes"] if n["kind"] == "formula")["facts"]["peril"]


def _by(d: dict, kind: str) -> list[dict]:
    return [n for n in d["nodes"] if n["kind"] == kind]


def _region_cell(payload: dict, tid: str) -> tuple[str, dict]:
    """The exposure cell of the region with the most policies, as the frozen formula lists it."""
    from services.governance.s2701 import REGION_ROW
    sf = payload["s2701"]["standard_formula_natcat"]
    peril, line = max(((p, x) for p, r in sf["perils"].items() if r.get("available") and p != "subsidence"
                       for x in r["regions"] if x["region"] in REGION_ROW.get(p, {})), key=lambda t: t[1]["n_policies"])
    import services.regspec as R
    spec = R.load("sii_qrt_natcat", payload["_specs"]["sii_qrt_natcat"]["version"])
    row = REGION_ROW[peril][line["region"]]
    return f"{tid}.{row}.{_col(spec, tid, peril, 'exposure')}", line


def _col(spec: dict, tid: str, peril: str, role: str) -> str:
    """The column of a peril's block with this role (exposure, after, …)."""
    import services.regspec as R
    from services.governance.s2701 import _COL_ROLE, _peril_of
    return next(c["id"] for c in R.template(spec, tid)["columns"]
                if _peril_of(c["section"]) == peril and _COL_ROLE.get(c["label"]) == role)


def test_a_solo_cell_traces_from_the_law_to_the_book(api):
    maker, checker, _ = _users(api)
    from services.governance.filings import reporting_period_end
    pe = reporting_period_end(api.s, IBERIA)
    state_method(api.s, IBERIA, pe)
    _state(api, maker, checker, pe, TREATY, SEGUROS)
    fid, payload = _generate(api, maker, "insurer_solvency", SEGUROS)
    assert all("reporting_entity_id" in p for p in payload["policies"])        # frozen: whose book each policy is

    cell, line = _region_cell(payload, "S2701")
    d = _trace(api, maker, fid, cell)
    assert d["supported"] and d["layers"] == ["law", "spec", "cell", "basis", "book", "source"]
    assert {n["layer"] for n in d["nodes"]} == set(d["layers"])
    ids = {n["id"] for n in d["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in d["edges"])

    act = next(n for n in _by(d, "act") if n["facts"]["role"] == "template")
    assert act["quote"]["found_in"] == "32023R0894" and act["facts"]["text_held"]
    ins = _by(d, "instruction")
    assert ins and all(i["quote"]["found_in"] == "32023R0894" for i in ins)        # the cell's own instruction, verbatim
    assert next(n for n in _by(d, "act") if n["facts"]["role"] == "formula")["facts"]["text_held"]

    # the policies the formula placed in the region tie to the printed exposure and count
    tie = d["cell"]["tie"]
    assert tie["ties"] and tie["printed_exposure"] == line["exposure_eur"] and tie["traced_n"] == line["n_policies"]
    pols = _by(d, "policy")
    more = _by(d, "more")
    assert len(pols) + sum(m["facts"]["hidden"] for m in more) == line["n_policies"]
    assert all(p["facts"]["sum_insured"] > 0 for p in pols)
    run = next(n for n in d["nodes"] if n["id"] == "run")
    assert run["facts"]["fingerprint"] and run["facts"]["books"][0]["n_assets"] > 0
    assert any(e["target"] == "run" for e in d["edges"])

    # exposure is before mitigation: no statement; the cell after mitigation rests on the attested treaty, who and when
    assert not _by(d, "statement")
    import services.regspec as R
    spec = R.load("sii_qrt_natcat", payload["_specs"]["sii_qrt_natcat"]["version"])
    row = cell.split(".")[1]
    d2 = _trace(api, maker, fid, f"S2701.{row}.{_col(spec, 'S2701', _peril(d), 'after')}")
    st = _by(d2, "statement")
    assert set(TREATY.values()) <= {s["facts"]["value"] for s in st}       # with any reinstatement terms attested
    assert all(s["id"].removeprefix("stmt-provided.").startswith("ri_") for s in st)
    assert all(s["facts"]["attested_by"] == "approver@iberia.demo" and s["facts"]["attested_at"] for s in st)

    # capped: the summary cell reads every policy; the 'more' node expands
    whole = _trace(api, maker, fid, "S2701.R0010.C0010")
    m = _by(whole, "more")
    if m:
        g = m[0]["facts"]["group"]
        wider = _trace(api, maker, fid, "S2701.R0010.C0010", expand=f"{g}:1")
        assert len(_by(wider, "policy")) > len(_by(whole, "policy"))

    # refused: a cell the template greys, one it does not print, the group template's cell on a solo report
    for bad, code in ((f"S2701.{row}.C0001", "trace.cell.greyed"), ("S2701.R9999.C0010", "trace.cell.unknown"),
                      ("S2704.R0010.C0010", "trace.cell.unknown")):
        r = api.get(f"/v1/filings/{fid}/trace", headers=maker, params={"cell": bad})
        assert r.status_code == 404 and r.json()["error"]["error"] == code, (bad, r.text)


def test_a_group_cell_traces_through_each_undertaking_and_its_method(api):
    maker, checker, _ = _users(api)
    from services.governance.filings import reporting_period_end
    pe = reporting_period_end(api.s, IBERIA)
    state_method(api.s, IBERIA, pe)
    _state(api, maker, checker, pe, TREATY, GROUP)
    _method(api, maker, checker, pe, SEGUROS, "method_1")
    _method(api, maker, checker, pe, IBERIA_RE, "method_2")
    fid, payload = _generate(api, maker, "insurer_solvency", GROUP)
    ents = {e["entity_id"]: e for e in payload["_consolidation"]["entities"]}
    assert ents[SEGUROS]["weight"] == 1.0 and ents[IBERIA_RE]["weight"] == 0.0       # method 2: out of this template

    cell, line = _region_cell(payload, "S2704")
    d = _trace(api, maker, fid, cell)
    methods = {n["label"]: n["facts"] for n in _by(d, "method")}
    assert {k: v["method"].split(" — ")[0] for k, v in methods.items()} == {"Iberia Mutual Seguros": "Method 1",
                                                                             "Iberia Re": "Method 2"}
    assert all(v["attested_by"] == "approver@iberia.demo" for v in methods.values())
    und = {n["label"]: n for n in _by(d, "undertaking")}
    assert und["Iberia Re"]["tone"] == "out" and und["Iberia Re"]["facts"]["n_policies"] == 0
    assert und["Iberia Re"]["facts"]["n_policies_left_out"] > 0
    assert und["Iberia Re"]["msgs"][0]["code"] == "trace.book.left_out"
    assert und["Iberia Mutual Seguros"]["facts"]["n_policies"] == line["n_policies"]
    assert d["cell"]["tie"]["ties"]
    # every policy shown hangs off the undertaking it belongs to
    seg = und["Iberia Mutual Seguros"]["id"]
    for p in _by(d, "policy"):
        assert {"source": seg, "target": p["id"]} in d["edges"] and p["facts"]["undertaking"] == "Iberia Mutual Seguros"


def test_a_template_5_cell_traces_to_its_exposures_their_scores_and_feeds(api):
    """Pillar 3 Template 5: the cell → the instruction naming its column → the at-risk level the bank stated (who attested
    it) → the exposures it sums, tying to the printed value → the hazard scores they sit on → the feeds."""
    from tests.integration.conftest import login
    from tests.integration.test_pillar3_report import _new_filing
    h = login(api, "admin@meridian.demo", "Demo!admin1")
    fid = _new_filing(api, h)
    v = api.get(f"/v1/filings/{fid}/lineage/t5", headers=h).json()
    row = next(r["id"] for r in v["rows"] if v["cells"]["ALL"][r["id"]].get("h"))
    form = api.get(f"/v1/filings/{fid}/form", headers=h).json()["annex"]["sections"]
    keys = {c.get("trace") for s in form if s.get("key") == "t5" for r in s["rows"] for c in r.get("cells") or []}
    assert f"T5.{row}.h" in keys                                     # the form's cell carries its trace key

    d = _trace(api, h, fid, f"T5.{row}.h")
    assert d["supported"] and d["cell"]["tie"]["ties"] and d["cell"]["value"] == v["cells"]["ALL"][row]["h"]
    ins = _by(d, "instruction")
    assert ins and all("column h" in i["facts"]["ref"] or "columns c" in i["facts"]["ref"] for i in ins)
    assert all(i["quote"]["found_in"] for i in ins)                  # quoted word for word from the stored ITS
    level = next(s for s in _by(d, "statement") if s["id"] == "stmt-method.at_risk_level")
    assert level["facts"]["value"] == 50            # the test fixture's stated level (money_method: no attester recorded)
    exp = _by(d, "exposure")
    assert exp and len(exp) + sum(m["facts"]["hidden"] for m in _by(d, "more")) == d["cell"]["tie"]["traced_n"]
    scores = _by(d, "score")
    assert scores and all(any(e["source"].startswith("exposure-") and e["target"] == s["id"] for e in d["edges"]) for s in scores)
    assert _by(d, "feed") and all(any(e["source"] == s["id"] for e in d["edges"]) for s in scores if _by(d, "feed"))
    geo = next(g["code"] for g in v["geographies"] if g["code"] != "ALL")
    assert _trace(api, h, fid, f"T5.{row}.b@{geo}")["supported"]
    for col in [c["id"] for c in v["columns"]]:                        # every column the form prints for the row
        t = _trace(api, h, fid, f"T5.{row}.{col}")
        assert t["supported"] and t["cell"]["tie"]["ties"], (col, t["cell"]["tie"])
    r = api.get(f"/v1/filings/{fid}/trace", headers=h, params={"cell": "T5.999.b"})
    assert r.status_code == 404 and r.json()["error"]["error"] == "trace.cell.unknown"


def test_a_premium_cell_is_a_statement_not_a_figure_of_the_book(api):
    """An other-region premium cell is entered by the filer: its trace has the statement (or that it is missing), never
    policies of the book."""
    maker, checker, _ = _users(api)
    from services.governance.filings import reporting_period_end
    pe = reporting_period_end(api.s, IBERIA)
    state_method(api.s, IBERIA, pe)
    fid, payload = _generate(api, maker, "insurer_solvency", SEGUROS)
    import services.regspec as R
    from services.governance import s2701
    spec = R.load("sii_qrt_natcat", payload["_specs"]["sii_qrt_natcat"]["version"])
    n, row = next(iter(s2701.other_region_rows(spec)["windstorm"].items()))
    cell = f"S2701.{row}.{s2701.premium_column(spec)['windstorm']}"
    d = _trace(api, maker, fid, cell)
    assert not _by(d, "policy") and not _by(d, "undertaking")
    st = _by(d, "statement")
    attested = {a["key"].removeprefix("provided.") for a in payload["_provided_attested"]}
    if cell in attested:
        assert st[0]["facts"]["attested_by"]
    else:
        assert st[0]["msgs"][0]["code"] == "trace.gap.premium_not_stated"
        assert not any(m["code"] == "trace.book.premium_stated" for m in _by(d, "formula")[0].get("msgs", []))


def test_a_half_year_template_5_cell_traces_on_its_own_period(api):
    """Pillar 3 twice a year (E354): the group's half-year report traces like the year's — its Template 5 cells tie to
    their exposures, and the trace carries the half-year the filing froze."""
    from services.governance import periods as P
    from tests.integration.conftest import login
    from tests.integration.filers import group, half_year_without_statements
    from tests.integration.test_e2e_p3_semiannual import _post_state
    from tests.integration.test_intake_pipeline import BANK_ORG
    maker, checker = login(api, "admin@meridian.demo", "Demo!admin1"), login(api, "approver@meridian.demo", "Demo!approve1")
    s = api.s
    h = half_year_without_statements(s, BANK_ORG)
    state_method(s, BANK_ORG, h)
    s.execute(text("UPDATE regulatory_filing SET status = 'superseded' WHERE org_id = CAST(:o AS uuid) AND framework = 'bank_p3esg' "
                   "AND status NOT IN ('superseded', 'withdrawn')"), {"o": BANK_ORG})
    grp = group(s, BANK_ORG)
    _post_state(api, maker, checker, "large_institution", "large", grp, h)
    _post_state(api, maker, checker, "listed_institution", "listed", grp, h)
    half = [o for o in api.get("/v1/obligations", headers=maker).json()["obligations"] if o["period_kind"] == "half_year"]
    pf = api.get(f"/v1/filings/preflight?framework=bank_p3esg&entity_id={grp}", headers=maker).json()
    g = api.post("/v1/filings", headers=maker, json={"framework": "bank_p3esg", "confirm_token": pf["confirm_token"],
                                                     "entity_id": grp, "obligation_id": half[0]["obligation_id"]})
    assert g.status_code == 201, g.text
    fid = g.json()["filing_id"]
    v = api.get(f"/v1/filings/{fid}/lineage/t5", headers=maker).json()
    assert v["supported"], v
    row = next(r["id"] for r in v["rows"] if v["cells"]["ALL"][r["id"]].get("b"))
    d = _trace(api, maker, fid, f"T5.{row}.b")
    assert d["supported"] and d["cell"]["tie"]["ties"]
    assert d["filing"]["period_label"] == P.label(h, P.HALF_YEAR) and d["filing"]["period"] == P.view(h, P.HALF_YEAR)
    assert d["cell"]["period"]["kind"] == "half_year"
    assert _by(d, "statement")[0]["facts"]["value"] == 50                 # the at-risk threshold stated for the half-year
    from tests.integration.test_pillar3_report import _payload
    assert _payload(s, fid)["method"]["period_end"] == h.isoformat()       # the method the figures read is the half-year's
