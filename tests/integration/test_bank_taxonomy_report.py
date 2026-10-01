"""The credit institution's EU Taxonomy Art. 8 report (report type bank_tcfd) prints the Annex VI templates and nothing
else (E95), end to end through the HTTP API:

  a new filing freezes the loan book the templates read (no physical-risk scores, no PCAF / TCFD / credit-risk sections);
  its form is Template 0's main KPIs, its annex every template of the governing version; it exports JSON and XLSX, and
  an XBRL request is refused (no official binding is held); a filing frozen under the earlier report shape still
  renders — the templates, then what it froze, marked; the bank's KRI page loads both sets with their anchors.

Reads the demo bank's loan book (Meridian) inside one rolled-back transaction: the filings, snapshots and engine runs it
writes are never committed.
"""
from __future__ import annotations

import io
import json
import zipfile

import pytest
from sqlalchemy import text

from services.governance.bank_taxonomy_report import EARLIER, EARLIER_KEYS, ENGINE_FIELDS
from tests.integration.conftest import login as _login
from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration
_NOT_TAXONOMY = ("TCFD", "PCAF", "expected loss", "Transition risk", "physical climate risk", "stranding")


def _new_filing(api, maker) -> str:
    api.s.execute(text("UPDATE regulatory_filing SET status = 'superseded' WHERE org_id = CAST(:o AS uuid) "
                       "AND framework = 'bank_tcfd' AND status NOT IN ('superseded', 'withdrawn')"), {"o": BANK_ORG})
    pf = api.get("/v1/filings/preflight?framework=bank_tcfd", headers=maker).json()
    assert pf["value_at_risk_eur"] is None and pf["coverage"]["label"] == "exposures with a gross carrying amount"
    g = api.post("/v1/filings", headers=maker, json={"framework": "bank_tcfd", "confirm_token": pf["confirm_token"]})
    assert g.status_code == 201, g.text
    return g.json()["filing_id"]


def _payload(s, fid: str) -> dict:
    return s.execute(text("""SELECT s.payload FROM regulatory_filing f JOIN report_snapshots s ON s.snapshot_id = f.snapshot_id
                             WHERE f.filing_id = CAST(:f AS uuid)"""), {"f": fid}).scalar()


def test_a_new_filing_carries_only_the_taxonomy_templates(api):
    maker = _login(api, "admin@meridian.demo", "Demo!admin1")
    fid = _new_filing(api, maker)
    p = _payload(api.s, fid)
    # frozen: the book the templates read, its count and total, the method — and the records every filing carries
    assert {k for k in p if not k.startswith("_")} == {"assets", "rollup", "method"}
    assert not set(EARLIER_KEYS) & set(p) and set(p["rollup"]) == {"n_assets", "total_value_eur"}
    assert p["assets"] and not any(set(ENGINE_FIELDS) & set(a) for a in p["assets"])
    assert p["_specs"]["bank_taxonomy"]["version"]

    form = api.get(f"/v1/filings/{fid}/form", headers=maker).json()
    keys = {d["key"] for g in form["groups"] for d in g["datapoints"]}
    assert keys == {"taxonomy.gar_stock.turnover", "taxonomy.gar_stock.capex", "taxonomy.gar_stock.coverage", "book.n_assets"}
    secs = form["annex"]["sections"]
    assert secs and all((x.get("spec") or {}).get("framework") == "bank_taxonomy" for x in secs)
    text_ = json.dumps(form["annex"], ensure_ascii=False)
    assert not any(w in text_ for w in _NOT_TAXONOMY)

    r = api.get(f"/v1/filings/{fid}/export?format=xbrl", headers=maker)
    assert r.status_code == 409 and "not an available format" in r.text
    r = api.get(f"/v1/filings/{fid}/export?format=xlsx", headers=maker)
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    sheets = " ".join(zf.read(n).decode("utf-8", "ignore") for n in zf.namelist() if n.startswith("xl/"))
    assert "Summary of KPIs" in sheets and not any(w in sheets for w in ("TCFD", "PCAF", "headline_score"))
    assert api.get(f"/v1/filings/{fid}/export?format=json", headers=maker).status_code == 200
    # no hazard cell to trace: the lineage says what the report traces instead
    lin = api.get(f"/v1/filings/{fid}/lineage?hazard=flood", headers=maker).json()
    assert lin["supported"] is False and "Taxonomy" in lin["message"]


def test_a_filing_of_the_earlier_report_shape_still_renders(api):
    """A bank_tcfd filing frozen before E95 carried the whole bank disclosure snapshot (rollup, by_hazard, PCAF, the
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
           **{k: v for k, v in new.items() if k.startswith("_")}}            # what the earlier builder froze
    sid = s.execute(text("""INSERT INTO report_snapshots (org_id, report_type, version, reporting_basis, payload, payload_sha256)
                            VALUES (CAST(:o AS uuid), 'bank_tcfd', 9001, CAST(:b AS jsonb), CAST(:p AS jsonb), :h)
                            RETURNING snapshot_id::text"""),
                    {"o": BANK_ORG, "b": json.dumps(basis), "p": json.dumps(old, default=str), "h": _sha256(old)}).scalar()
    s.execute(text("ALTER TABLE regulatory_filing DISABLE TRIGGER USER"))
    s.execute(text("UPDATE regulatory_filing SET snapshot_id = CAST(:s AS uuid) WHERE filing_id = CAST(:f AS uuid)"),
              {"s": sid, "f": fid})
    s.execute(text("ALTER TABLE regulatory_filing ENABLE TRIGGER USER"))

    form = api.get(f"/v1/filings/{fid}/form", headers=maker).json()
    groups = [g["group"] for g in form["groups"]]
    assert groups[0].startswith("Summary of KPIs") and any(g.startswith(EARLIER) for g in groups)
    secs = form["annex"]["sections"]
    tx = [x for x in secs if (x.get("spec") or {}).get("framework") == "bank_taxonomy"]
    earlier = [x for x in secs if x["title"].startswith(EARLIER)]
    assert tx and earlier and secs.index(tx[-1]) < secs.index(earlier[0])          # the templates first
    assert all("earlier shape of this report" in x["note"] for x in earlier)
    assert any("physical climate risk" in x["title"] for x in earlier)
    for fmt in ("json", "xlsx"):
        assert api.get(f"/v1/filings/{fid}/export?format={fmt}", headers=maker).status_code == 200
    assert api.get(f"/v1/filings/{fid}/export?format=xbrl", headers=maker).status_code == 409


def test_the_bank_kri_page_loads_both_sets_with_their_anchors(api):
    maker = _login(api, "admin@meridian.demo", "Demo!admin1")
    fws = api.get("/v1/reg-tasks/kri/frameworks", headers=maker).json()["frameworks"]
    assert {f["framework"]: f["label"] for f in fws} == {"bank_tcfd": "EU Taxonomy Art. 8", "bank_p3esg": "Pillar 3 ESG"}

    tx = api.get("/v1/reg-tasks/kri?framework=bank_tcfd", headers=maker).json()
    assert tx["supported"] and tx["label"] == "EU Taxonomy Art. 8 KRIs"
    k = {x["key"]: x for x in tx["kpis"]}
    for key in ("gar", "gar_capex", "gar_coverage"):                        # printed by Template 0: a filed basis
        assert k[key]["live_only"] is False and "Template 0" in k[key]["filed_basis"] and "Template 0" in k[key]["reg"]
    for key in ("value_at_risk", "fin_emissions", "expected_loss", "taxonomy"):
        if key in k:
            assert k[key]["live_only"] is True and not k[key].get("reg")    # no TCFD tag, no filed history
    assert not any("TCFD" in (x.get("reg") or "") + (x.get("filed_basis") or "") for x in tx["kpis"])
    assert all({f["key"] for f in h["figures"]} == {"gar", "gar_capex", "gar_coverage"} for h in tx["history"])
    d = api.get("/v1/reg-tasks/kri/detail?framework=bank_tcfd&kri=value_at_risk", headers=maker).json()
    assert d["trend"]["points"] == []                                        # live only: no filed trend

    p3 = api.get("/v1/reg-tasks/kri?framework=bank_p3esg", headers=maker).json()
    k = {x["key"]: x for x in p3["kpis"]}
    assert k["fin_emissions"]["live_only"] is False and "Template 1" in k["fin_emissions"]["filed_basis"]
    assert k["value_at_risk"]["live_only"] is True and "Template 5" in k["value_at_risk"]["filed_basis"]
