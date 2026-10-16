"""Suite-wide guard (error log E2): the test run must leave the demo database exactly as it found it.

A fingerprint of the demo business tables (content) and of the append-only records (row counts) is taken when the run
starts and compared when it ends. For the whole run the guard holds the scheduled feed-refresh lock (E178), so the
platform's own scheduled writes wait instead of reading as a leak. A test that commits and does not clean up — or writes through a path that commits —
fails the whole run, naming the table, instead of silently leaving data behind (as 202 fact rows and four renamed demo
sites once were). Skipped when the database is unreachable. Set TELLUMEN_SKIP_DB_GUARD=1 to bypass deliberately.
"""
from __future__ import annotations

import os

import pytest

# content-fingerprinted: business data a test must never change
_CONTENT = {
    "organizations": "org_id",
    "reporting_entities": "entity_id",
    "portfolio_entities": "entity_id",
    "sc_company_sites": "site_id",
    "sc_sourcing_plots": "plot_id",
    "org_reporting_settings": "org_id",
}
# count-fingerprinted: append-only / governed records a test must not leave behind
_COUNTED = ("asset_observations", "asset_conflicts", "engine_runs", "report_snapshots", "regulatory_filing",
            "approval_requests", "provided_datapoint", "reg_early_signal", "reg_act_relation", "reg_detected_change",
            "ingest_batches", "intake_files", "regspec_signoff")


def _fingerprint() -> dict | None:
    try:
        from sqlalchemy import text

        from core.db.session import get_session
        with get_session() as s:
            fp = {}
            for t, pk in _CONTENT.items():
                fp[t] = s.execute(text(f"SELECT md5(COALESCE(string_agg(x::text, '|' ORDER BY x.{pk}), '')) FROM {t} x")).scalar()
            for t in _COUNTED:
                fp[f"{t} (rows)"] = s.execute(text(f"SELECT count(*) FROM {t}")).scalar()
            return fp
    except Exception:  # noqa: BLE001 — no database: nothing to guard
        return None


_START: dict | None = None
_SCHEDULE_LOCK = None     # a dedicated connection holding the scheduled-refresh lock for the whole run (E178)


def _hold_the_schedule() -> None:
    """Wait for any scheduled feed refresh in flight, then keep the next ones out until the run ends (E178): the
    platform's own scheduled writes would otherwise read as a leaking test. Waits at most 20 minutes."""
    global _SCHEDULE_LOCK
    try:
        from sqlalchemy import text

        from core.db.config import engine
        from services.data.feeds import SCHEDULED_REFRESH_LOCK
        c = engine.connect()
        c.execute(text("SET lock_timeout = '20min'"))
        c.execute(text("SELECT pg_advisory_lock(:k)"), {"k": SCHEDULED_REFRESH_LOCK})
        _SCHEDULE_LOCK = c
    except Exception:  # noqa: BLE001 — no database: nothing to hold
        _SCHEDULE_LOCK = None


def pytest_sessionstart(session):
    global _START
    if os.environ.get("TELLUMEN_SKIP_DB_GUARD") != "1" and not os.environ.get("PYTEST_XDIST_WORKER"):
        _hold_the_schedule()
        _START = _fingerprint()


def pytest_sessionfinish(session, exitstatus):
    if _START is None or os.environ.get("PYTEST_XDIST_WORKER"):
        return
    end = _fingerprint()
    if _SCHEDULE_LOCK is not None:            # a pooled connection keeps a session lock: release it, then return it
        from sqlalchemy import text

        from services.data.feeds import SCHEDULED_REFRESH_LOCK
        _SCHEDULE_LOCK.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": SCHEDULED_REFRESH_LOCK})
        _SCHEDULE_LOCK.execute(text("RESET lock_timeout"))
        _SCHEDULE_LOCK.commit()
        _SCHEDULE_LOCK.close()
    if end is None:
        return
    changed = [k for k in _START if _START[k] != end.get(k)]
    if changed:
        rep = session.config.pluginmanager.get_plugin("terminalreporter")
        detail = ", ".join(f"{k}: {_START[k]} → {end[k]}" if "(rows)" in k else k for k in changed)
        if rep:
            rep.write_line(f"\nDEMO-DATA GUARD FAILED — the test run changed: {detail}", red=True, bold=True)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
