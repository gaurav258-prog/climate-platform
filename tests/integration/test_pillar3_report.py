"""Pillar 3 ESG prints what its ITS templates print (E97), and its Template 5 rows carry KRIs with filed history (E98) —
end to end through the HTTP API, on the demo bank's banking book (Meridian), inside one rolled-back transaction: the
method it reads is the one this test states (E85), and the filings, snapshots and runs it writes are never committed.
"""
from __future__ import annotations

import io
import json
import zipfile

import pytest
from sqlalchemy import text

from services.governance import kri_t5
from services.governance.pillar3_report import EARLIER, EARLIER_KEYS, NOT_FROZEN
from tests.integration.conftest import login as _login
from tests.integration.money_method import state_method
from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration
_NOT_PRINTED = ("expected loss", "stranding", "TCFD", "Headline exposure", "Value at material physical risk")


def _new_filing(api, maker) -> str:
    from services.governance.filings import reporting_period_end
    state_method(api.s, BANK_ORG, reporting_period_end(api.s, BANK_ORG))
    api.s.execute(text("UPDATE regulatory_filing SET status = 'superseded' WHERE org_id = CAST(:o AS uuid) "
                       "AND framework = 'bank_p3esg' AND status NOT IN ('superseded', 'withdrawn')"), {"o": BANK_ORG})
    pf = api.get("/v1/filings/preflight?framework=bank_p3esg", headers=maker).json()
    assert pf["value_at_risk_eur"] is None and pf["coverage"]["label"] == "exposures scored"
    g = api.post("/v1/filings", headers=maker, json={"framework": "bank_p3esg", "confirm_token": pf["confirm_token"]})
    assert g.status_code == 201, g.text
    return g.json()["filing_id"]


def _payload(s, fid: str) -> dict:
    return s.execute(text("""SELECT s.payload FROM regulatory_filing f JOIN report_snapshots s ON s.snapshot_id = f.snapshot_id
                             WHERE f.filing_id = CAST(:f AS uuid)"""), {"f": fid}).scalar()


def test_a_new_pillar3_filing_carries_only_what_the_templates_print(api):
    maker = _login(api, "admin@meridian.demo", "Demo!admin1")
    fid = _new_filing(api, maker)
    p = _payload(api.s, fid)
    # Template 1 columns i-k read the institution's statements (E103) — the EVIC-based PCAF figure is not frozen any more
    assert {k for k in p if not k.startswith("_")} == {"assets", "rollup", "t1_emissions", "method"}
    assert set(p["rollup"]) == {"n_assets", "n_scored", "total_value_eur"} and not set(EARLIER_KEYS) & set(p)
    assert p["assets"] and all(a.get("hazards") is not None and not set(NOT_FROZEN) & set(a) for a in p["assets"])
    assert [u["key"] for u in p["method"]["used"]] == ["method.at_risk_level"]      # the one parameter the templates read

    form = api.get(f"/v1/filings/{fid}/form", headers=maker).json()
    assert [g["group"] for g in form["groups"]] == ["Template 1 · financed emissions (total row)", "Frozen banking book"]
    titles = [x["title"] for x in form["annex"]["sections"]]
    assert all(t.startswith("Template") for t in titles), titles
    assert not any(w in json.dumps(form, ensure_ascii=False) for w in _NOT_PRINTED)

    r = api.get(f"/v1/filings/{fid}/export?format=xlsx", headers=maker)
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    sheets = " ".join(zf.read(n).decode("utf-8", "ignore") for n in zf.namelist() if n.startswith("xl/"))
    assert "Template 5" in sheets and "outstanding_loan_balance_eur" in sheets
    assert not any(w in sheets for w in ("expected loss", "stranding", "TCFD"))
    assert api.get(f"/v1/filings/{fid}/export?format=json", headers=maker).status_code == 200


def test_a_pillar3_filing_of_the_earlier_shape_still_renders(api):
    """A filing frozen before E97 carried the whole bank disclosure snapshot (rollup, by_hazard, Taxonomy summary, the
    credit-risk overlays). Its form, annex and exports render what it froze — the templates first, the rest marked."""
    from api.routers.bank import build_disclosure_snapshot
    from services.governance.report_snapshots import _sha256
    maker = _login(api, "admin@meridian.demo", "Demo!admin1")
    s = api.s
    fid = _new_filing(api, maker)
    new = _payload(s, fid)
    basis = s.execute(text("""SELECT s.reporting_basis FROM regulatory_filing f JOIN report_snapshots s
                              ON s.snapshot_id = f.snapshot_id WHERE f.filing_id = CAST(:f AS uuid)"""), {"f": fid}).scalar()
    old = {**build_disclosure_snapshot(s, BANK_ORG, basis["scenario"], basis["horizon"]),
           "expected_loss": {"annual_el_eur": 1_000, "total_ead_eur": 2_000, "annual_el_bps": 5, "lifetime_el_eur": 3_000,
                             "lifetime_el_bps": 15, "scenario": "disorderly_2c"},   # frozen on unscoped filings (stated here)
           **{k: v for k, v in new.items() if k.startswith("_")}}
    old = json.loads(json.dumps(old, default=str))
    sid = s.execute(text("""INSERT INTO report_snapshots (org_id, report_type, version, reporting_basis, payload, payload_sha256)
                            VALUES (CAST(:o AS uuid), 'bank_p3esg', 9001, CAST(:b AS jsonb), CAST(:p AS jsonb), :h)
                            RETURNING snapshot_id::text"""),
                    {"o": BANK_ORG, "b": json.dumps(basis), "p": json.dumps(old), "h": _sha256(old)}).scalar()
    s.execute(text("ALTER TABLE regulatory_filing DISABLE TRIGGER USER"))
    s.execute(text("UPDATE regulatory_filing SET snapshot_id = CAST(:s AS uuid) WHERE filing_id = CAST(:f AS uuid)"),
              {"s": sid, "f": fid})
    s.execute(text("ALTER TABLE regulatory_filing ENABLE TRIGGER USER"))

    form = api.get(f"/v1/filings/{fid}/form", headers=maker).json()
    groups = [g["group"] for g in form["groups"]]
    assert groups[:2] == ["Financed emissions (PCAF)", "Frozen banking book"]
    assert f"{EARLIER} · Headline exposure" in groups
    secs = form["annex"]["sections"]
    earlier = [x for x in secs if x["title"].startswith(EARLIER)]
    templates = [x for x in secs if x["title"].startswith("Template")]
    assert templates and earlier and secs.index(templates[-1]) < secs.index(earlier[0])
    assert any("expected loss" in x["title"] for x in earlier) and all("earlier shape" in x["note"] for x in earlier)
    for fmt in ("json", "xlsx"):
        assert api.get(f"/v1/filings/{fid}/export?format={fmt}", headers=maker).status_code == 200
    assert api.get(f"/v1/filings/{fid}/export?format=xbrl", headers=maker).status_code == 409    # an old filing too (E104)


def test_template5_rows_carry_kris_with_their_filed_history(api):
    maker = _login(api, "admin@meridian.demo", "Demo!admin1")
    fid = _new_filing(api, maker)
    p = _payload(api.s, fid)
    r = api.get("/v1/reg-tasks/kri?framework=bank_p3esg", headers=maker).json()
    rows = [k for k in r["kpis"] if k.get("group") == kri_t5.GROUP]
    from services.governance.filing_annex import _p3_spec
    t5 = next(t for t in _p3_spec(p)["templates"] if t["id"] == "T5")
    assert len(rows) == 3 * len(t5["rows"])                                  # one per printed row and column h, i, j
    assert all(not k["live_only"] and "Template 5" in k["filed_basis"] and k["reg"].startswith("Template 5") for k in rows)
    assert all(not k.get("group") for k in r["kpis"] if not k["key"].startswith("t5."))

    # the filed history: this filing's printed cells, read from its frozen grid
    h = next(x for x in r["history"] if x["filing_id"] == fid)
    filed = {f["key"]: f["value"] for f in h["figures"] if f.get("group") == kri_t5.GROUP}
    grid = kri_t5.grid(p)
    for row in grid["rows"]:
        for col, _ in kri_t5.COLUMNS:
            v = row["values"][col]
            assert filed[kri_t5.key(row["id"], col)] == (None if v is None else round(v))
    # the live value is computed the same way: on an unchanged book it equals what was just filed
    live = {k["key"]: k["value"] for k in rows}
    assert live == filed
    # a row's KRI opens with its trend across filings
    k = next(k for k in rows if k["value"])
    d = api.get(f"/v1/reg-tasks/kri/detail?framework=bank_p3esg&kri={k['key']}", headers=maker).json()
    assert any(pt["filing_id"] == fid and pt["value"] == filed[k["key"]] for pt in d["trend"]["points"])
