"""Lane 2 attested values are baked into the frozen filing payload, not joined live at read time (2026-09-24
fix, platform E2E audit finding #6): create_snapshot() used to leave "Provided & attested" out of the hash-
verified payload entirely — filings.form_view()/get_filing() computed it live from provided_datapoint on
every single read. That meant an already-accepted/attested filing's Provided & attested section could
silently change if a NEW value was attested afterward for the same framework — a real break in the
immutability guarantee every other section of a frozen filing has. Fixed: create_snapshot() bakes
attested_values() into payload["_provided_attested"] at freeze time (now part of the sha256-verified
content); form_view() reads that frozen list instead of calling attested_values() live.

Requires PostgreSQL. Non-polluting: each test rolls back its session on exit, on a throwaway future period.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

import services.governance.provided_data as P
from core.db.session import get_session
from services.governance import filings as F
from services.governance.report_snapshots import create_snapshot

BANK_ORG = "11111111-1111-4111-8111-111111111111"
FUTURE_PERIOD = "2095-12-31"   # distinct from other filing-lifecycle throwaway periods


def _u(s, email):
    return str(s.execute(text("SELECT user_id FROM users WHERE email=:e"), {"e": email}).scalar())


def _attest_taxonomy_value(s, value: float, maker: str, checker: str) -> dict:
    """Submit + immediately attest a fresh taxonomy_aligned provided value, superseding any live one."""
    r = P.submit(s, BANK_ORG, maker, framework="bank_tcfd", datapoint_key="taxonomy_aligned",
                value_num=value, unit="%", source="client")
    payload = s.execute(text("SELECT payload FROM approval_requests WHERE request_id=:r"),
                        {"r": r["approval_request_id"]}).scalar()
    return P.attest(s, BANK_ORG, payload, "approved", checker)


@pytest.mark.integration
def test_snapshot_bakes_in_the_attested_value_at_freeze_time():
    with get_session() as s:
        maker, checker = _u(s, "admin@meridian.demo"), _u(s, "approver@meridian.demo")
        _attest_taxonomy_value(s, 18.5, maker, checker)
        snap = create_snapshot(s, BANK_ORG, "bank_tcfd", maker)
        payload = s.execute(text("SELECT payload FROM report_snapshots WHERE snapshot_id=CAST(:i AS uuid)"),
                            {"i": snap["snapshot_id"]}).scalar()
        provided = payload.get("_provided_attested") or []
        row = next((p for p in provided if p["key"] == "provided.taxonomy_aligned"), None)
        assert row is not None and row["value"] == 18.5
        s.rollback()


@pytest.mark.integration
def test_form_view_shows_the_frozen_value_not_a_later_attestation():
    """The exact bug proved: attest a value, freeze a filing, THEN attest a DIFFERENT value for the same
    datapoint — the already-frozen filing's form must keep showing the ORIGINAL value, never the new one."""
    with get_session() as s:
        maker, checker = _u(s, "admin@meridian.demo"), _u(s, "approver@meridian.demo")
        _attest_taxonomy_value(s, 18.5, maker, checker)

        snap = create_snapshot(s, BANK_ORG, "bank_tcfd", maker)
        fid = s.execute(text("""
            INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, snapshot_id, created_by)
            VALUES (:o, 'bank_tcfd', :pe, 'FY2095-provided', 'accepted', :snap, :u) RETURNING filing_id::text
        """), {"o": BANK_ORG, "pe": FUTURE_PERIOD, "snap": snap["snapshot_id"], "u": maker}).scalar()

        # a DIFFERENT value gets attested afterward, for the SAME framework/datapoint
        _attest_taxonomy_value(s, 42.0, maker, checker)

        out = F.form_view(s, BANK_ORG, fid)
        provided_group = next((g for g in out["groups"] if g["group"] == "Provided & attested (customer / vendor)"), None)
        assert provided_group is not None
        dp = next(d for d in provided_group["datapoints"] if d["key"] == "provided.taxonomy_aligned")
        assert dp["value"] == 18.5, "an already-frozen filing must never pick up a later attestation"
        s.rollback()


@pytest.mark.integration
def test_a_filing_frozen_before_the_fix_shows_nothing_rather_than_being_backfilled():
    """A frozen payload with no _provided_attested key at all (pre-fix filing) must show an empty section,
    never retroactively populated with live data that was never actually part of what was frozen.
    report_snapshots is WORM (UPDATE is DB-trigger-blocked, confirmed by this test's own first attempt at
    writing it) — the pre-fix scenario is simulated the only way it's honestly reachable: a payload that
    never had the key from the moment it was inserted, via a direct INSERT bypassing create_snapshot()
    (which now always adds it)."""
    import json
    with get_session() as s:
        maker = _u(s, "admin@meridian.demo")
        payload = {"rollup": {"total_value_eur": 1000}}   # deliberately no "_provided_attested" key
        snap_id = s.execute(text("""
            INSERT INTO report_snapshots (org_id, report_type, version, reporting_basis, payload, created_by, payload_sha256)
            VALUES (:o, 'bank_tcfd', 999, '{}'::jsonb, CAST(:p AS jsonb), :u, 'test-fixture-hash')
            RETURNING snapshot_id
        """), {"o": BANK_ORG, "p": json.dumps(payload), "u": maker}).scalar()
        fid = s.execute(text("""
            INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, snapshot_id, created_by)
            VALUES (:o, 'bank_tcfd', :pe, 'FY2093-prefix', 'accepted', :snap, :u) RETURNING filing_id::text
        """), {"o": BANK_ORG, "pe": "2093-12-31", "snap": str(snap_id), "u": maker}).scalar()
        out = F.form_view(s, BANK_ORG, fid)
        assert not any(g["group"] == "Provided & attested (customer / vendor)" for g in out["groups"])
        s.rollback()
