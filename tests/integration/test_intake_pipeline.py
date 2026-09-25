"""Customer data intake pipeline end to end, through the real HTTP routes (services/intake/pipeline.py).

Principles under test (agreed 2026-09-25): every check passed → imported automatically; any failed check → a SECOND
person approves (maker ≠ checker) before anything lands, and the import then runs from the stored file; files refused
on security grounds are recorded but never kept; every state is recorded append-only.

Requires PostgreSQL. HTTP tests commit, so each cleans up its own rows (the append-only triggers are disabled only
inside the cleanup transaction).
"""
from __future__ import annotations

import json
import os
import uuid

import pandas as pd
import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.intake import storage

BANK_ORG = "11111111-1111-4111-8111-111111111111"
EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


def _rows(tag, n=4, bad=0):
    rows = [{"asset_name": f"TEST-PIPE-{tag}-{i}", "asset_type": "commercial_real_estate", "latitude": 48.85 + i / 100,
             "longitude": 2.35, "appraised_value_eur": 1_000_000, "sector": "Commercial real estate",
             "counterparty_evic_eur": 100_000_000} for i in range(n)]
    for j in range(bad):
        rows.append({**rows[0], "asset_name": f"TEST-PIPE-{tag}-BAD{j}", "latitude": 999})
    return rows


def _csv(rows) -> bytes:
    return pd.DataFrame(rows).to_csv(index=False).encode()


def _purge(tag):
    """Remove everything a test created. The ledger is append-only in production; only this cleanup transaction
    lifts the triggers, and re-arms them before it commits."""
    with get_session() as s:
        s.execute(text("ALTER TABLE ingest_batch_events DISABLE TRIGGER trg_ingest_event_worm"))
        s.execute(text("ALTER TABLE intake_files DISABLE TRIGGER trg_intake_file_protect"))
        ids = [r[0] for r in s.execute(text("SELECT entity_id FROM portfolio_entities WHERE entity_name LIKE :p"), {"p": f"TEST-PIPE-{tag}%"}).all()]
        if ids:
            s.execute(text("DELETE FROM ext_banking WHERE entity_id = ANY(:i)"), {"i": ids})
            s.execute(text("DELETE FROM portfolio_entities WHERE entity_id = ANY(:i)"), {"i": ids})
        batches = s.execute(text("SELECT batch_id, file_id, approval_request_id FROM ingest_batches WHERE filename LIKE :f"),
                            {"f": f"%{tag}%"}).all()
        file_ids = [f for _, f, _ in batches if f]
        shas = [r[0] for r in s.execute(text("SELECT sha256 FROM intake_files WHERE file_id = ANY(:i) AND storage_uri LIKE 'local://%'"),
                                        {"i": file_ids}).all()] if file_ids else []
        for b, f, a in batches:
            s.execute(text("DELETE FROM ingest_batches WHERE batch_id = :b"), {"b": b})
            if a:
                s.execute(text("DELETE FROM approval_requests WHERE request_id = :a"), {"a": a})
        if file_ids:
            s.execute(text("DELETE FROM intake_files WHERE file_id = ANY(:i)"), {"i": file_ids})
        s.execute(text("ALTER TABLE ingest_batch_events ENABLE TRIGGER trg_ingest_event_worm"))
        s.execute(text("ALTER TABLE intake_files ENABLE TRIGGER trg_intake_file_protect"))
        s.commit()
    for sha in set(shas):
        try:
            with get_session() as s:
                still = s.execute(text("SELECT 1 FROM intake_files WHERE sha256 = :s LIMIT 1"), {"s": sha}).first()
            if not still:
                os.remove(storage._path_for(sha))
        except OSError:
            pass


def _landed(tag):
    with get_session() as s:
        return s.execute(text("SELECT count(*) FROM portfolio_entities WHERE entity_name LIKE :p"), {"p": f"TEST-PIPE-{tag}%"}).scalar()


def _events(batch_id):
    with get_session() as s:
        return [r[0] for r in s.execute(text("SELECT to_state FROM ingest_batch_events WHERE batch_id = CAST(:b AS uuid) ORDER BY at"),
                                        {"b": batch_id}).all()]


@pytest.fixture()
def tag():
    t = uuid.uuid4().hex[:8]
    yield t
    _purge(t)


@pytest.mark.integration
def test_clean_file_imports_automatically_and_is_stored_write_once(intake_client, tag):
    raw = _csv(_rows(tag))
    r = intake_client.post("/v1/bank/assets/upload", headers=intake_client.maker, files={"file": (f"{tag}.csv", raw)},
                    data={"declared_row_count": "4", "declared_totals": json.dumps({"appraised_value_eur": 4_000_000})})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["state"] == "imported" and b["n_uploaded"] == 4 and b["controls"]["landing"]["status"] == "pass"
    assert _landed(tag) == 4
    assert _events(b["batch_id"]) == ["received", "checked", "imported"]
    led = intake_client.get(f"/v1/intake/batches/{b['batch_id']}", headers=intake_client.maker).json()
    assert led["security_status"] == "passed" and led["storage_uri"].startswith("local://")
    assert storage.get(led["file_sha256"]) == raw                     # exactly what was received, kept


@pytest.mark.integration
def test_failed_check_needs_a_reason_then_a_second_person(intake_client, tag):
    raw = _csv(_rows(tag, n=4, bad=1))       # 1 of 5 rows invalid → 20% rejected → a check fails
    r0 = intake_client.post("/v1/bank/assets/upload", headers=intake_client.maker, files={"file": (f"{tag}.csv", raw)})
    assert r0.status_code == 409 and r0.json()["error"]["error"] == "approval_reason_required"
    with get_session() as s:                 # nothing persisted for a request that was simply incomplete
        assert s.execute(text("SELECT count(*) FROM ingest_batches WHERE filename = :f"), {"f": f"{tag}.csv"}).scalar() == 0

    r = intake_client.post("/v1/bank/assets/upload", headers=intake_client.maker, files={"file": (f"{tag}.csv", raw)},
                    data={"approval_reason": "The invalid row is a closed loan; the rest are current exposures"})
    assert r.status_code == 202, r.text
    b = r.json()
    assert b["state"] == "awaiting_approval" and _landed(tag) == 0    # nothing lands before approval

    own = intake_client.post(f"/v1/approvals/{b['approval_request_id']}/decide", headers=intake_client.maker,
                      json={"decision": "approved", "reason": "self"})
    assert own.status_code == 422                                     # the sender can never approve their own batch

    ok = intake_client.post(f"/v1/approvals/{b['approval_request_id']}/decide", headers=intake_client.checker,
                     json={"decision": "approved", "reason": "Checked the rejected row against the servicing system"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["applied"]["state"] == "imported" and ok.json()["applied"]["n_landed"] == 4
    assert _landed(tag) == 4
    assert _events(b["batch_id"]) == ["received", "checked", "awaiting_approval", "imported"]


@pytest.mark.integration
def test_rejected_approval_lands_nothing(intake_client, tag):
    raw = _csv(_rows(tag, n=4, bad=1))
    b = intake_client.post("/v1/bank/assets/upload", headers=intake_client.maker, files={"file": (f"{tag}.csv", raw)},
                    data={"approval_reason": "Please review the one invalid row"}).json()
    d = intake_client.post(f"/v1/approvals/{b['approval_request_id']}/decide", headers=intake_client.checker,
                    json={"decision": "rejected", "reason": "Invalid row must be fixed at source"})
    assert d.status_code == 200 and d.json()["applied"]["state"] == "rejected"
    assert _landed(tag) == 0 and _events(b["batch_id"])[-1] == "rejected"


@pytest.mark.integration
def test_the_same_file_twice_needs_approval(intake_client, tag):
    raw = _csv(_rows(tag))
    assert intake_client.post("/v1/bank/assets/upload", headers=intake_client.maker, files={"file": (f"{tag}.csv", raw)}).status_code == 200
    again = intake_client.post("/v1/bank/assets/upload", headers=intake_client.maker, files={"file": (f"{tag}.csv", raw)})
    assert again.status_code == 409
    assert any("identical file was imported" in x for x in again.json()["error"]["controls"]["gate"]["reasons"])
    assert _landed(tag) == 4


@pytest.mark.integration
def test_security_refusal_is_recorded_but_the_file_is_not_kept(intake_client, tag):
    r = intake_client.post("/v1/bank/assets/upload", headers=intake_client.maker, files={"file": (f"{tag}.xlsm", b"PK\x03\x04junk")})
    assert r.status_code == 422 and r.json()["error"]["error"] == "security_blocked"
    led = intake_client.get(f"/v1/intake/batches/{r.json()['error']['batch_id']}", headers=intake_client.maker).json()
    assert led["state"] == "rejected" and led["storage_uri"] == "not-retained:security"


@pytest.mark.integration
def test_infected_file_is_refused_and_not_kept(intake_client, tag, monkeypatch):
    from services.intake import malware
    monkeypatch.setattr(malware, "scan", lambda raw, timeout=60.0: {"status": "infected", "signature": "Eicar-Test-Signature", "engine": "ClamAV test"})
    r = intake_client.post("/v1/bank/assets/upload", headers=intake_client.maker, files={"file": (f"{tag}.csv", _csv(_rows(tag)) + EICAR)})
    assert r.status_code == 422 and r.json()["error"]["error"] == "malware_detected"
    led = intake_client.get(f"/v1/intake/batches/{r.json()['error']['batch_id']}", headers=intake_client.maker).json()
    assert led["malware_status"] == "infected" and led["storage_uri"] == "not-retained:security" and _landed(tag) == 0


@pytest.mark.integration
def test_held_when_a_required_scan_is_unavailable_then_resumed(intake_client, tag, monkeypatch):
    from services.intake import malware
    monkeypatch.setattr(malware.settings, "INTAKE_REQUIRE_MALWARE_SCAN", True)
    monkeypatch.setattr(malware, "scan", lambda raw, timeout=60.0: {"status": "not_configured", "signature": None, "engine": None})
    r = intake_client.post("/v1/bank/assets/upload", headers=intake_client.maker, files={"file": (f"{tag}.csv", _csv(_rows(tag)))})
    assert r.status_code == 202 and r.json()["state"] == "held" and _landed(tag) == 0

    monkeypatch.setattr(malware, "scan", lambda raw, timeout=60.0: {"status": "clean", "signature": None, "engine": "ClamAV test"})
    res = intake_client.post(f"/v1/intake/batches/{r.json()['batch_id']}/rescan", headers=intake_client.maker)
    assert res.status_code == 200, res.text
    assert res.json()["state"] == "imported" and _landed(tag) == 4
    assert _events(r.json()["batch_id"]) == ["received", "held", "checked", "imported"]


@pytest.mark.integration
def test_api_push_goes_through_the_same_pipeline(intake_client, tag):
    tok = intake_client.post("/v1/ingest/tokens", headers=intake_client.maker, json={"name": f"TEST-PIPE-{tag}"}).json()
    raw_token = tok.get("token") or tok.get("raw_token")
    h = {"Authorization": f"Bearer {raw_token}"}
    try:
        rows = _rows(tag)
        bad = intake_client.post("/v1/ingest/bank/assets", headers=h, json={"rows": rows, "declared_totals": {"appraised_value_eur": 9_999_999}})
        assert bad.status_code == 202 and bad.json()["state"] == "awaiting_approval"   # token owner is the maker
        ok = intake_client.post("/v1/ingest/bank/assets", headers=h, json={"rows": _rows(tag + "b")})
        assert ok.status_code == 200 and ok.json()["n_uploaded"] == 4
    finally:
        intake_client.delete(f"/v1/ingest/tokens/{tok['token_id']}", headers=intake_client.maker)
        with get_session() as s:
            s.execute(text("UPDATE ingest_batches SET filename = :f WHERE filename = :a"), {"f": f"api-{tag}", "a": f"api:{tok['token_id']}"})
            s.commit()


@pytest.mark.integration
def test_history_and_file_identity_cannot_be_rewritten(intake_client, tag):
    b = intake_client.post("/v1/bank/assets/upload", headers=intake_client.maker, files={"file": (f"{tag}.csv", _csv(_rows(tag)))}).json()
    with get_session() as s:
        with pytest.raises(Exception, match="append-only"):
            s.execute(text("UPDATE ingest_batch_events SET to_state = 'x' WHERE batch_id = CAST(:b AS uuid)"), {"b": b["batch_id"]})
        s.rollback()
        with pytest.raises(Exception, match="immutable"):
            s.execute(text("UPDATE intake_files SET sha256 = 'x' WHERE original_name = :f"), {"f": f"{tag}.csv"})
        s.rollback()
        with pytest.raises(Exception, match="DELETE is blocked"):
            s.execute(text("DELETE FROM intake_files WHERE original_name = :f"), {"f": f"{tag}.csv"})
        s.rollback()
        with pytest.raises(Exception, match="ck_ingest_batch_4eyes"):
            s.execute(text("UPDATE ingest_batches SET gate_status = 'needs_signoff' WHERE batch_id = CAST(:b AS uuid)"), {"b": b["batch_id"]})
        s.rollback()


SECTOR_FILES = {
    "/v1/realestate/properties/validate": lambda t, i, bad: {
        "property_name": f"TEST-PIPE-{t}-{i}", "latitude": 51.9 + i / 100, "longitude": 4.47,
        "property_value_eur": 42_000_000, "annual_noi_eur": "abc" if bad else 2_400_000, "property_type": "logistics"},
    "/v1/assetmgmt/holdings/validate": lambda t, i, bad: {
        "holding_name": f"TEST-PIPE-{t}-{i}", "sector": "Energy", "latitude": 52.0 + i / 100, "longitude": 4.4,
        "position_value_eur": "abc" if bad else 5_000_000},
    "/v1/insurance/policies/validate": lambda t, i, bad: {
        "policy_name": f"TEST-PIPE-{t}-{i}", "latitude": 39.4 + i / 100, "longitude": -0.37,
        "sum_insured_eur": "abc" if bad else 3_700_000},
}


@pytest.mark.integration
@pytest.mark.parametrize("path", sorted(SECTOR_FILES))
def test_every_sector_previews_the_same_checks(intake_client, tag, path):
    rows = [SECTOR_FILES[path](tag, i, bad=(i == 0)) for i in range(4)]
    r = intake_client.post(path, headers=intake_client.maker, files={"file": (f"{tag}.csv", _csv(rows))})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["n_error"] == 1 and b["n_valid"] == 3 and b["security"]["status"] == "passed"
    assert b["controls"]["gate"]["status"] == "needs_signoff"
