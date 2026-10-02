"""EUDR end to end (E108), through the HTTP API in one rolled-back transaction (Terra Foods; maker / checker; the satellite
engine stubbed):

  intake       suppliers, plots, the shipment and its plots through the governed intake (layer 2)
  records      the undertaking's status, a reading, legality evidence, the risk assessment — four eyes (layer 3)
  checks       blocking until each is in place; the generic preflight refuses (prepared from the shipment)
  filing       prepared → four eyes → attested → submitted → reference made available → 'accepted'; the shipment is frozen
  window       amend / withdraw within 72 hours of the reference (IR 2024/3084 Art. 5(1)); closed once the product is
               placed on the market or exported (5(3)(b)); an authority's extension no later than 8 days (5(4))
  amend        within the window: superseded by a new draft of the same shipment; the draft is refreshed after a correction
  rejected     a statement the authority rejects (Art. 8) is 'rejected'
  exports      the form and the Annex II layout; JSON
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest
from sqlalchemy import text

from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration
TERRA = "55555555-5555-4555-8555-555555555555"
POLY = {"type": "Polygon", "coordinates": [[[-1.606123, 6.694123], [-1.604123, 6.694123], [-1.604123, 6.696123],
                                            [-1.606123, 6.696123], [-1.606123, 6.694123]]]}


def _no_loss(footprint, cutoff_year, min_treecover_pct, point_buffer_m, **_):
    return SimpleNamespace(insufficient=False, loss_pixels=0, total_pixels=400, loss_ha=0.0, first_loss_year=None,
                           tile="10N_010W", source="GFC-test", forest_pixels=300)


def _upload(api, h, book, rows):
    r = api.post(f"/v1/eudr/intake/{book}/upload", headers=h,
                 files={"file": (f"{book}.csv", pd.DataFrame(rows).to_csv(index=False).encode(), "text/csv")},
                 data={"approval_reason": "E2E"})
    assert r.status_code == 200 and r.json()["state"] == "imported", r.text[:500]


def _approve(api, checker, rid):
    d = api.post(f"/v1/approvals/{rid}/decide", headers=checker, json={"decision": "approved", "reason": "checked"})
    assert d.status_code == 200, d.text


def _file(api, maker, checker, fid):
    sr = api.post(f"/v1/filings/{fid}/submit-for-review", headers=maker)
    assert sr.status_code == 200, sr.text
    _approve(api, checker, sr.json()["approval_request_id"])
    unsigned = api.post(f"/v1/filings/{fid}/attest", headers=checker, json={"statement": "Signed for Terra Foods."})
    assert unsigned.status_code == 409 and "Annex II point 6" in unsigned.text        # name and function (Annex II point 6)
    at = api.post(f"/v1/filings/{fid}/attest", headers=checker,
                  json={"statement": "Signed for and on behalf of Terra Foods.", "function": "Head of Sourcing Compliance"})
    assert at.status_code == 200, at.text
    assert api.post(f"/v1/filings/{fid}/submit", headers=maker, json={"submission_ref": "EUDR-IS"}).status_code == 200


def test_a_shipment_is_stated_filed_referenced_amended_and_withdrawn(api, monkeypatch):
    from services.intelligence import forest
    monkeypatch.setattr(forest, "forest_loss_since", _no_loss)
    s, tag = api.s, uuid.uuid4().hex[:6]
    maker, checker = _login(api, "analyst@terra.demo", "Demo!analyst1"), _login(api, "approver@terra.demo", "Demo!approve1")

    # intake: the supplier, a plot, the shipment and its plot
    _upload(api, maker, "eudr_suppliers", [{"party_name": "Ashanti Co-op", "party_ref": f"S-{tag}", "address": "PO Box 1, Kumasi",
                                            "contact_email": "co@op.example", "country": "GH"}])
    from services.intake import pipeline
    plot = {"plot_name": f"E2E {tag}", "plot_geojson": json.dumps(POLY), "commodity": "Cocoa", "annual_spend_eur": "1000",
            "external_ref": f"P-{tag}", "supplier_ref": f"S-{tag}", "country": "GH", "currency": "EUR", "book_date": "2025-12-31"}
    admin = s.execute(text("SELECT user_id::text FROM users WHERE email = 'admin@terra.demo'")).scalar()
    out = pipeline.submit(s, TERRA, "supply_plots", pd.DataFrame([plot]).to_csv(index=False).encode(), f"{tag}.csv", user_id=admin)
    assert out["state"] == "imported", out.get("errors")
    _upload(api, maker, "eudr_movements", [{"movement_ref": f"M-{tag}", "movement_kind": "placing", "actor_role": "operator",
                                            "planned_on": "2027-01-15", "hs_code": "180100", "description": "Cocoa beans",
                                            "customs_flow": "true", "net_mass_kg": "25000", "supplier_ref": f"S-{tag}"}])
    _upload(api, maker, "eudr_movement_plots", [{"movement_ref": f"M-{tag}", "plot_ref": f"P-{tag}",
                                                 "production_from": "2026-01-01", "production_to": "2026-06-30"}])
    m = s.execute(text("SELECT movement_id::text FROM eudr_movement WHERE external_ref = :r"), {"r": f"M-{tag}"}).scalar()
    pid = s.execute(text("SELECT plot_id::text FROM sc_sourcing_plots WHERE external_ref = :r"), {"r": f"P-{tag}"}).scalar()

    # nothing can be prepared yet; the generic preflight sends you to the shipment
    pre = api.post(f"/v1/eudr/movements/{m}/filing", headers=maker, json={})
    assert pre.status_code == 409 and "cannot be prepared yet" in pre.text
    g = api.get("/v1/filings/preflight?framework=eudr_dds", headers=maker)
    assert g.status_code in (400, 409, 422) and "from its shipment" in g.text

    # the records
    r = api.post("/v1/eudr/status", headers=maker, json={"effective_from": "2026-12-30", "size_class": "large", "country": "ES",
                                                        "address": "Calle Mayor 1, Madrid", "eori": "ESB12345678"})
    _approve(api, checker, r.json()["approval_request_id"])
    from services.eudr import reading
    reading.record(s, TERRA, pid, None)
    assert api.post("/v1/eudr/evidence", headers=maker, json={"aspect": "land_use_rights", "document_kind": "Land title",
                                                             "plot_id": pid}).status_code == 201
    from services.eudr.records import CRITERIA
    r = api.post(f"/v1/eudr/movements/{m}/risk-assessment", headers=maker, json={
        "path": "full", "conclusion": "negligible", "criteria": {k: f"assessed {k}" for k in CRITERIA}})
    _approve(api, checker, r.json()["approval_request_id"])

    # prepared, filed through four eyes, referenced
    p = api.post(f"/v1/eudr/movements/{m}/filing", headers=maker, json={"note": "first shipment"})
    assert p.status_code == 201, p.text
    fid = p.json()["filing_id"]
    assert api.post(f"/v1/eudr/movements/{m}/filing", headers=maker, json={}).status_code == 409     # one live statement
    v = api.get(f"/v1/filings/{fid}/validation", headers=maker).json()
    assert v["passed"], [f for f in v["findings"] if not f["passed"] and f["severity"] == "blocking"]
    _file(api, maker, checker, fid)
    # accepted only by the reference number the information system made available — never by the generic step
    acc = api.post(f"/v1/filings/{fid}/accept", headers=maker, json={"ack_ref": "x"})
    assert acc.status_code == 409 and "reference number" in acc.text
    assert api.post("/v1/eudr/intake/eudr_movements/upload", headers=maker, files={"file": ("m.csv", pd.DataFrame([{
        "movement_ref": f"M-{tag}", "movement_kind": "placing", "actor_role": "operator", "planned_on": "2027-01-15",
        "hs_code": "180100", "description": "Cocoa beans", "customs_flow": "true", "net_mass_kg": "1"}]).to_csv(index=False).encode(),
        "text/csv")}, data={"approval_reason": "x"}).status_code in (200, 422)                    # refused row, or held
    assert float(s.execute(text("SELECT net_mass_kg FROM eudr_movement WHERE movement_id = CAST(:m AS uuid)"), {"m": m}).scalar()) == 25000
    ref = api.post(f"/v1/eudr/filings/{fid}/reference", headers=maker,
                   json={"reference_number": f"27ESXX{tag.upper()}", "verification_number": "V9", "source": "manual_entry"})
    assert ref.status_code == 200 and ref.json()["status"] == "accepted", ref.text
    w = api.get(f"/v1/eudr/filings/{fid}/window", headers=maker).json()["window"]
    assert w["open"] is True

    # the authority's extension: no later than 8 days after the reference
    late = datetime.now(timezone.utc) + timedelta(days=9)
    assert api.post(f"/v1/eudr/filings/{fid}/events", headers=maker,
                    json={"kind": "window_extended", "until": late.isoformat()}).status_code == 409

    # amend within the window: a new draft supersedes it; the shipment can be corrected and the draft refreshed
    a = api.post(f"/v1/eudr/filings/{fid}/amend", headers=maker, json={"note": "net mass corrected"})
    assert a.status_code == 201, a.text
    fid2 = a.json()["filing_id"]
    assert s.execute(text("SELECT status FROM regulatory_filing WHERE filing_id = CAST(:f AS uuid)"), {"f": fid}).scalar() == "superseded"
    s.execute(text("UPDATE eudr_movement SET net_mass_kg = 24800 WHERE movement_id = CAST(:m AS uuid)"), {"m": m})
    rf = api.post(f"/v1/eudr/filings/{fid2}/refresh", headers=maker, json={})
    assert rf.status_code == 200, rf.text
    fid3 = rf.json()["filing_id"]
    filed = api.get(f"/v1/filings/{fid3}/export?format=json", headers=maker).json()
    assert filed["payload"]["statement"]["annex_ii"]["2"]["quantity"]["net_mass_kg"] == 24800.0
    _file(api, maker, checker, fid3)
    api.post(f"/v1/eudr/filings/{fid3}/reference", headers=maker, json={"reference_number": f"27ESYY{tag.upper()}"})

    # placed on the market: the window closes
    assert api.post(f"/v1/eudr/filings/{fid3}/events", headers=maker, json={"kind": "placed_or_exported"}).status_code == 201
    wd = api.post(f"/v1/eudr/filings/{fid3}/withdraw", headers=maker, json={"reason": "a mistake found after placing"})
    assert wd.status_code == 409 and "placed on the market or exported" in wd.text

    # dated and named by its shipment: no scenario, horizon or money; the assurance pack says what it rests on
    f3 = api.get(f"/v1/filings/{fid3}", headers=maker).json()
    assert f3["period_label"] == f"M-{tag} · 2027-01-15" and f3["own_flow"]["own_page"] == "/eudr"
    basis = f3["snapshot"]["reporting_basis"]
    assert basis["shipment"] == f"M-{tag}" and basis["reporting_period_end"] == "2027-01-15" and "scenario" not in basis
    pack = api.get(f"/v1/filings/{fid3}/assurance-pack", headers=maker)
    assert pack.status_code == 200, pack.text[:300]
    import io as _io
    import zipfile
    md = zipfile.ZipFile(_io.BytesIO(pack.content)).read("methodology.md").decode()
    assert "shipment M-" in md and "never a verdict" in md and "None" not in md

    # the official form, Annex II item by item
    form = api.get(f"/v1/filings/{fid3}/form", headers=maker).json()
    annex = next(x for x in form["annex"]["sections"] if x.get("key") == "eudr_annex_ii")
    labels = [r["cells"][0]["text"] for r in annex["rows"]]
    printed = [t for t in labels if t]                       # each point's printed words, once, from the captured spec
    assert [t.split(".")[0] for t in printed] == ["1", "2", "3", "5", "6"]               # point 4 deleted by 2025/2650
    assert printed[2].startswith("3. Country of production and the geolocation of all plots of land")
    assert "deleted" in (annex.get("note") or "")
    six = [r["cells"][1]["text"] for r in annex["rows"][labels.index(printed[-1]):]]            # point 6, as signed
    assert six[0].startswith("Signed for and on behalf of: ") and six[1].startswith("Date: ")
    assert six[2].endswith(", Head of Sourcing Compliance") and six[3].startswith("Signature: attested in the platform by ")


def _submitted(s) -> str:
    """A filed statement as the information system holds it before the reference number (only the status matters here)."""
    m = s.execute(text("""INSERT INTO eudr_movement (org_id, kind, actor_role, planned_on, hs_code, description, customs_flow,
                                                  net_mass_kg)
                          VALUES (CAST(:o AS uuid), 'placing', 'operator', '2027-01-15', '180100', 'Cocoa beans', true, 1000)
                          RETURNING movement_id::text"""), {"o": TERRA}).scalar()
    return s.execute(text("""INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, eudr_movement_id)
                             VALUES (CAST(:o AS uuid), 'eudr_dds', '2027-12-31', 'T · 2027-12-31', 'submitted', CAST(:m AS uuid))
                             RETURNING filing_id::text"""), {"o": TERRA, "m": m}).scalar()


def _status(s, fid) -> str:
    return s.execute(text("SELECT status FROM regulatory_filing WHERE filing_id = CAST(:f AS uuid)"), {"f": fid}).scalar()


def test_withdrawn_within_the_window(api):
    """IR 2024/3084 Art. 5(1): withdrawn within 72 hours after the reference number was made available."""
    s, maker = api.s, _login(api, "analyst@terra.demo", "Demo!analyst1")
    fid = _submitted(s)
    assert api.post(f"/v1/eudr/filings/{fid}/withdraw", headers=maker, json={"reason": "no reference yet, so no"}).status_code == 409
    assert api.post(f"/v1/eudr/filings/{fid}/reference", headers=maker, json={"reference_number": "27ESWD1"}).status_code == 200
    assert api.post(f"/v1/eudr/filings/{fid}/withdraw", headers=maker, json={"reason": "short"}).status_code in (409, 422)
    w = api.post(f"/v1/eudr/filings/{fid}/withdraw", headers=maker, json={"reason": "wrong plot linked to the shipment"})
    assert w.status_code == 200, w.text
    assert _status(s, fid) == "withdrawn"
    assert api.post(f"/v1/eudr/filings/{fid}/amend", headers=maker, json={}).status_code == 409


def test_rejected_only_before_the_reference(api):
    """IR 2024/3084 Art. 8(1): rejection 'shall no longer be possible once the reference number … has become available';
    8(2): the product is then 'deemed not covered by a Due Diligence Statement'."""
    s, maker = api.s, _login(api, "analyst@terra.demo", "Demo!analyst1")
    fid = _submitted(s)
    r = api.post(f"/v1/eudr/filings/{fid}/events", headers=maker, json={"kind": "rejected", "detail": "incomplete geolocation"})
    assert r.status_code == 201, r.text
    assert _status(s, fid) == "rejected"
    late = _submitted(s)
    api.post(f"/v1/eudr/filings/{late}/reference", headers=maker, json={"reference_number": "27ESRJ1"})
    assert api.post(f"/v1/eudr/filings/{late}/events", headers=maker, json={"kind": "rejected"}).status_code == 409
    assert _status(s, late) == "accepted"


def test_the_database_holds_the_same_rules(api):
    """The database itself, not only the service: a statement names its shipment; it is accepted only with its reference
    number recorded; no rejection once referenced; no withdrawal of a submitted statement."""
    import psycopg
    s = api.s
    fid = _submitted(s)
    s.execute(text("INSERT INTO eudr_dds_event (filing_id, kind, detail) VALUES (CAST(:f AS uuid), 'reference_received', 'X')"),
              {"f": fid})
    with pytest.raises(Exception), s.begin_nested():
        s.execute(text("""INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status)
                          VALUES (CAST(:o AS uuid), 'eudr_dds', '2028-12-31', 'FY2028', 'draft')"""), {"o": TERRA})
    unref = _submitted(s)
    with pytest.raises(Exception) as e, s.begin_nested():
        s.execute(text("UPDATE regulatory_filing SET status = 'accepted' WHERE filing_id = CAST(:f AS uuid)"), {"f": unref})
    assert isinstance(e.value.orig, psycopg.errors.RaiseException)
    for to in ("rejected", "withdrawn"):
        with pytest.raises(Exception) as e, s.begin_nested():
            s.execute(text("UPDATE regulatory_filing SET status = :t WHERE filing_id = CAST(:f AS uuid)"), {"t": to, "f": fid})
        assert isinstance(e.value.orig, psycopg.errors.RaiseException)
