"""Intake controls end to end (2026-09-25): receipt → transformation → gate → landing, and the ingest_batches ledger.

Why this exists: only the bank upload ran the row validator on IMPORT — insurance / real-estate / holdings imports
silently dropped any row whose number didn't parse and reported only a count, and even the bank path accepted
"1,250,000" in validation but then read it as missing in the ingestion core. Every sector now runs the same gate.

Requires PostgreSQL. Service-level tests roll back; the HTTP tests clean up after themselves.
"""
from __future__ import annotations

import io
import json
import uuid

import pandas as pd
import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.ingest.batches import GateError, begin_import, preview_controls

BANK_ORG = "11111111-1111-4111-8111-111111111111"
BANK_SPECS = None


def _specs():
    from api.routers.bank import ASSET_TEMPLATE_FIELDS
    return ASSET_TEMPLATE_FIELDS


def _rows(tag, n=4, value="1,000,000"):
    return [{"asset_name": f"TEST-INTAKE-{tag}-{i}", "asset_type": "commercial_real_estate", "latitude": 48.85 + i / 100,
             "longitude": 2.35, "appraised_value_eur": value, "sector": "Commercial real estate",
             "counterparty_evic_eur": 100_000_000} for i in range(n)]


def _raw(rows):
    return json.dumps(rows, sort_keys=True).encode()


def _user(s):
    return str(s.execute(text("SELECT user_id FROM users WHERE email='admin@meridian.demo'")).scalar())


# ───────────────────────────── service level (rolled back) ─────────────────────────────

@pytest.mark.integration
def test_clean_batch_lands_and_the_landing_check_is_recorded():
    with get_session() as s:
        rows = _rows(uuid.uuid4().hex[:6])
        df = pd.DataFrame(rows)
        ctl = begin_import(s, BANK_ORG, _user(s), "bank_assets", _raw(rows), df, _specs(), filename="t.csv",
                           value_field="appraised_value_eur")
        assert ctl.controls["gate"]["status"] == "pass"
        # the thousands separator was normalised BEFORE the engine sees it
        assert ctl.clean_df["appraised_value_eur"].tolist() == [1_000_000.0] * 4
        ctl.finish(s, n_landed=4, value_landed=4_000_000.0)
        b = s.execute(text("SELECT status, gate_status, landing->>'status' AS l FROM ingest_batches WHERE batch_id = CAST(:b AS uuid)"),
                      {"b": ctl.batch_id}).mappings().first()
        assert (b["status"], b["gate_status"], b["l"]) == ("imported", "pass", "pass")
        s.rollback()


@pytest.mark.integration
def test_a_repeat_file_needs_a_named_signoff_and_the_reason_is_recorded():
    with get_session() as s:
        uid = _user(s)
        rows = _rows(uuid.uuid4().hex[:6])
        df = pd.DataFrame(rows)
        first = begin_import(s, BANK_ORG, uid, "bank_assets", _raw(rows), df, _specs(), value_field="appraised_value_eur")
        first.finish(s, n_landed=4, value_landed=4_000_000.0)

        with pytest.raises(GateError) as e:
            begin_import(s, BANK_ORG, uid, "bank_assets", _raw(rows), df, _specs(), value_field="appraised_value_eur")
        assert e.value.code == "gate_signoff_required"
        assert any("already imported" in c["detail"] or "imported on" in c["detail"]
                   for c in e.value.controls["receipt"]["checks"] if c["status"] == "fail")

        with pytest.raises(GateError):   # a one-word reason is not a reason
            begin_import(s, BANK_ORG, uid, "bank_assets", _raw(rows), df, _specs(), value_field="appraised_value_eur", signoff_reason="ok")

        again = begin_import(s, BANK_ORG, uid, "bank_assets", _raw(rows), df, _specs(), value_field="appraised_value_eur",
                             signoff_reason="Correction re-send agreed with the loan-servicing team")
        row = s.execute(text("SELECT signoff_by::text, signoff_reason FROM ingest_batches WHERE batch_id = CAST(:b AS uuid)"),
                        {"b": again.batch_id}).mappings().first()
        assert row["signoff_by"] == uid and "loan-servicing" in row["signoff_reason"]
        s.rollback()


@pytest.mark.integration
def test_an_api_token_can_never_sign_off_and_an_empty_result_is_blocked():
    with get_session() as s:
        rows = _rows(uuid.uuid4().hex[:6])
        df = pd.DataFrame(rows)
        # declared totals that do not match → needs sign-off → a token (no user) is refused
        with pytest.raises(GateError) as e:
            begin_import(s, BANK_ORG, None, "bank_assets", _raw(rows), df, _specs(), via="api",
                         declared={"row_count": 99}, value_field="appraised_value_eur", signoff_reason="please accept this batch")
        assert e.value.code == "gate_signoff_required" and "API tokens cannot sign off" in e.value.message
        bad = pd.DataFrame([{**rows[0], "latitude": 999}])
        with pytest.raises(GateError) as e2:
            begin_import(s, BANK_ORG, _user(s), "bank_assets", _raw(rows), bad, _specs(), value_field="appraised_value_eur")
        assert e2.value.code == "gate_blocked"
        s.rollback()


@pytest.mark.integration
def test_the_ledger_itself_refuses_a_gated_batch_without_a_signoff():
    with get_session() as s:
        with pytest.raises(Exception, match="ck_ingest_batch_signoff"):
            s.execute(text("""INSERT INTO ingest_batches (org_id, template, sha256, n_total, n_valid, n_rejected, receipt, transform, gate_status)
                              VALUES (CAST(:o AS uuid), 't', 'x', 1, 1, 0, '{}', '{}', 'needs_signoff')"""), {"o": BANK_ORG})
        s.rollback()


@pytest.mark.integration
def test_european_decimal_comma_is_rejected_not_read_as_a_thousandth():
    with get_session() as s:
        rows = _rows(uuid.uuid4().hex[:6], value="1.234,5")
        ctl = preview_controls(s, BANK_ORG, "bank_assets", _raw(rows), pd.DataFrame(rows), _specs(), value_field="appraised_value_eur")
        assert ctl.report["n_valid"] == 0
        assert "decimal comma" in ctl.report["errors"][0]["problems"][0]
        assert ctl.controls["gate"]["status"] == "blocked"
        s.rollback()


# ───────────────────────────── HTTP (real router, cleaned up) ─────────────────────────────

def _csv(rows) -> bytes:
    return pd.DataFrame(rows).to_csv(index=False).encode()


@pytest.fixture()
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import app
    import services.tasks.jobs as jobs
    monkeypatch.setattr(jobs, "submit", lambda *a, **k: {"job": "stubbed-in-test"})   # never queue real scoring from a test
    with TestClient(app, raise_server_exceptions=False) as c:
        tok = c.post("/v1/auth/login", json={"email": "admin@meridian.demo", "password": "Demo!admin1"}).json()["access_token"]
        c.headers.update({"Authorization": f"Bearer {tok}"})
        yield c


def _cleanup(tag):
    with get_session() as s:
        ids = [r[0] for r in s.execute(text("SELECT entity_id FROM portfolio_entities WHERE org_id = CAST(:o AS uuid) AND entity_name LIKE :p"),
                                       {"o": BANK_ORG, "p": f"TEST-INTAKE-{tag}%"}).all()]
        if ids:
            s.execute(text("DELETE FROM ext_banking WHERE entity_id = ANY(:i)"), {"i": ids})
            s.execute(text("DELETE FROM portfolio_entities WHERE entity_id = ANY(:i)"), {"i": ids})
        s.execute(text("DELETE FROM ingest_batches WHERE org_id = CAST(:o AS uuid) AND filename = :f"), {"o": BANK_ORG, "f": f"TEST-INTAKE-{tag}.csv"})
        s.commit()


@pytest.mark.integration
def test_validate_returns_the_controls_and_writes_nothing(client):
    tag = uuid.uuid4().hex[:6]
    rows = _rows(tag)
    with get_session() as s:
        before = s.execute(text("SELECT count(*) FROM ingest_batches WHERE org_id = CAST(:o AS uuid)"), {"o": BANK_ORG}).scalar()
    r = client.post("/v1/bank/assets/validate", files={"file": (f"TEST-INTAKE-{tag}.csv", _csv(rows))},
                    data={"declared_row_count": "5", "declared_totals": json.dumps({"appraised_value_eur": 4_000_000})})
    assert r.status_code == 200, r.text
    c = r.json()["controls"]
    failed = {x["check"] for x in c["receipt"]["checks"] if x["status"] == "fail"}
    assert failed == {"declared_row_count"}            # 4 rows sent, 5 declared; the total (4,000,000) matches
    assert c["gate"]["status"] == "needs_signoff"
    with get_session() as s:
        after = s.execute(text("SELECT count(*) FROM ingest_batches WHERE org_id = CAST(:o AS uuid)"), {"o": BANK_ORG}).scalar()
    assert after == before


@pytest.mark.integration
def test_upload_end_to_end_gate_signoff_and_ledger(client):
    tag = uuid.uuid4().hex[:6]
    rows = _rows(tag)
    fname = f"TEST-INTAKE-{tag}.csv"
    try:
        r1 = client.post("/v1/bank/assets/upload", files={"file": (fname, _csv(rows))},
                         data={"declared_row_count": "4", "declared_totals": json.dumps({"appraised_value_eur": 4_000_000})})
        assert r1.status_code == 200, r1.text
        b1 = r1.json()
        assert b1["n_uploaded"] == 4 and b1["controls"]["gate"]["status"] == "pass"
        assert b1["controls"]["landing"]["status"] == "pass" and b1["controls"]["landing"]["n_landed"] == 4

        # the SAME file again → refused, with the reason and the full report
        r2 = client.post("/v1/bank/assets/upload", files={"file": (fname, _csv(rows))})
        assert r2.status_code == 409 and r2.json()["error"]["error"] == "gate_signoff_required"
        with get_session() as s:   # nothing landed on the refused attempt
            n = s.execute(text("SELECT count(*) FROM portfolio_entities WHERE org_id = CAST(:o AS uuid) AND entity_name LIKE :p"),
                          {"o": BANK_ORG, "p": f"TEST-INTAKE-{tag}%"}).scalar()
        assert n == 4

        # a named person accepts it, with a reason → lands, and the ledger says who and why
        r3 = client.post("/v1/bank/assets/upload", files={"file": (fname, _csv(rows))},
                         data={"signoff_reason": "Intentional re-load after the servicer restated balances"})
        assert r3.status_code == 200, r3.text
        led = client.get(f"/v1/intake/batches/{r3.json()['batch_id']}").json()
        assert led["gate_status"] == "needs_signoff" and "restated balances" in led["signoff_reason"] and led["status"] == "imported"
        assert any(b["batch_id"] == b1["batch_id"] for b in client.get("/v1/intake/batches").json()["batches"])
    finally:
        _cleanup(tag)


SECTOR_FILES = {
    "/v1/realestate/properties/validate": lambda i, bad: {
        "property_name": f"TEST-INTAKE-P{i}", "latitude": 51.9 + i / 100, "longitude": 4.47,
        "property_value_eur": 42_000_000, "annual_noi_eur": "abc" if bad else 2_400_000, "property_type": "logistics"},
    "/v1/assetmgmt/holdings/validate": lambda i, bad: {
        "holding_name": f"TEST-INTAKE-H{i}", "sector": "Energy", "latitude": 52.0 + i / 100, "longitude": 4.4,
        "position_value_eur": "abc" if bad else 5_000_000},
    "/v1/insurance/policies/validate": lambda i, bad: {
        "policy_name": f"TEST-INTAKE-S{i}", "latitude": 39.4 + i / 100, "longitude": -0.37,
        "sum_insured_eur": "abc" if bad else 3_700_000},
}


@pytest.mark.integration
@pytest.mark.parametrize("path", sorted(SECTOR_FILES))
def test_every_sector_previews_the_same_controls_and_names_the_value_a_bad_row_would_exclude(client, path):
    """Before this change only the bank import ran the row validator. The other sectors' imports silently skipped
    any row whose number did not parse. Now each exposes the controls — here a row whose value is "abc" is a
    rejected row with a reason, and the value share it excludes is stated."""
    mk = SECTOR_FILES[path]
    rows = [mk(i, bad=(i == 0)) for i in range(4)]
    r = client.post(path, files={"file": ("TEST-INTAKE.csv", _csv(rows))})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["n_error"] == 1 and b["n_valid"] == 3
    c = b["controls"]
    assert set(c) >= {"receipt", "transformation", "gate"}
    assert c["transformation"]["excluded"]["n_rows"] == 1
    assert c["gate"]["status"] == "needs_signoff"          # 25% of rows rejected is above the 5% limit
    assert any("rejected" in x for x in c["gate"]["reasons"])


@pytest.mark.integration
def test_a_row_dropped_after_validation_is_reported_by_the_landing_check_not_silent(client, monkeypatch):
    """An SoV row with a location but NO valuation passes validation (valuation columns are optional) and was then
    silently skipped by the import loop. It must now appear in the landing check as dropped."""
    import api.routers.insurance as ins
    monkeypatch.setattr(ins, "process_new_cells", lambda cells: {"scoring": "stubbed-in-test"})   # no real raster reads in a test
    tag = uuid.uuid4().hex[:6]
    rows = [{"policy_name": f"TEST-INTAKE-{tag}-{i}", "latitude": 39.4 + i / 100, "longitude": -0.37,
             "sum_insured_eur": 3_700_000 if i else None, "building_value_eur": None} for i in range(3)]
    try:
        r = client.post("/v1/insurance/policies/upload", files={"file": (f"TEST-INTAKE-{tag}.csv", _csv(rows))},
                        data={"signoff_reason": "Test: one location has no valuation yet"})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["n_uploaded"] == 2
        landing = b["controls"]["landing"]
        assert landing["status"] == "attention" and landing["n_dropped_after_validation"] == 1
    finally:
        with get_session() as s:
            ids = [x[0] for x in s.execute(text("SELECT entity_id FROM portfolio_entities WHERE org_id = CAST(:o AS uuid) AND entity_name LIKE :p"),
                                           {"o": BANK_ORG, "p": f"TEST-INTAKE-{tag}%"}).all()]
            if ids:
                s.execute(text("DELETE FROM ext_insurance WHERE entity_id = ANY(:i)"), {"i": ids})
                s.execute(text("DELETE FROM portfolio_entities WHERE entity_id = ANY(:i)"), {"i": ids})
            s.execute(text("DELETE FROM ingest_batches WHERE org_id = CAST(:o AS uuid) AND filename = :f"), {"o": BANK_ORG, "f": f"TEST-INTAKE-{tag}.csv"})
            s.commit()


@pytest.mark.integration
def test_api_push_enforces_declared_totals_and_a_token_cannot_override(client):
    tag = uuid.uuid4().hex[:6]
    rows = _rows(tag)
    tok = client.post("/v1/ingest/tokens", json={"name": f"TEST-INTAKE-{tag}"})
    assert tok.status_code == 201, tok.text
    token = tok.json()
    raw_token = next(v for k, v in token.items() if k in ("token", "raw_token"))
    hdr = {"Authorization": f"Bearer {raw_token}"}
    try:
        bad = client.post("/v1/ingest/bank/assets", headers=hdr, json={"rows": rows, "declared_row_count": 4,
                                                                        "declared_totals": {"appraised_value_eur": 9_999_999}})
        assert bad.status_code == 409 and bad.json()["error"]["error"] == "gate_signoff_required"
        assert "cannot sign off" in bad.json()["error"]["message"]
        ok = client.post("/v1/ingest/bank/assets", headers=hdr, json={"rows": rows, "declared_row_count": 4,
                                                                       "declared_totals": {"appraised_value_eur": 4_000_000}})
        assert ok.status_code == 200, ok.text
        assert ok.json()["ingested"] == 4 and ok.json()["controls"]["landing"]["status"] == "pass"
    finally:
        client.delete(f"/v1/ingest/tokens/{token['token_id']}")
        with get_session() as s:
            ids = [x[0] for x in s.execute(text("SELECT entity_id FROM portfolio_entities WHERE org_id = CAST(:o AS uuid) AND entity_name LIKE :p"),
                                           {"o": BANK_ORG, "p": f"TEST-INTAKE-{tag}%"}).all()]
            if ids:
                s.execute(text("DELETE FROM ext_banking WHERE entity_id = ANY(:i)"), {"i": ids})
                s.execute(text("DELETE FROM portfolio_entities WHERE entity_id = ANY(:i)"), {"i": ids})
            s.execute(text("DELETE FROM ingest_batches WHERE org_id = CAST(:o AS uuid) AND filename LIKE 'api:%' AND received_at > now() - interval '5 minutes' AND n_total = 4"), {"o": BANK_ORG})
            s.commit()
