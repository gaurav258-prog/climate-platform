"""Shared fixtures for the customer data intake tests."""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.intake import storage

_TOKENS: dict[str, dict] = {}


def _login(c, email, pw):
    """Log in once per test session: logging in before every test would trip the login rate limiter."""
    if email not in _TOKENS:
        r = c.post("/v1/auth/login", json={"email": email, "password": pw})
        _TOKENS[email] = {"Authorization": "Bearer " + r.json()["access_token"]}
    return _TOKENS[email]


@pytest.fixture()
def intake_client(monkeypatch):
    from fastapi.testclient import TestClient

    import services.tasks.jobs as jobs
    from api.main import app
    monkeypatch.setattr(jobs, "submit", lambda *a, **k: {"job": "stubbed-in-test"})   # never queue real scoring
    with TestClient(app, raise_server_exceptions=False) as c:
        c.maker = _login(c, "admin@meridian.demo", "Demo!admin1")
        c.checker = _login(c, "approver@meridian.demo", "Demo!approve1")
        yield c




def purge_observations(s, asset_ids) -> None:
    """Remove the asset facts a committed test recorded (intake phase 3). The history is append-only in production;
    only this cleanup transaction lifts its trigger, and re-arms it before the caller commits."""
    ids = [str(i) for i in asset_ids]
    if not ids:
        return
    s.execute(text("ALTER TABLE asset_observations DISABLE TRIGGER trg_asset_obs_worm"))
    s.execute(text("DELETE FROM asset_conflicts WHERE asset_id = ANY(CAST(:i AS uuid[]))"), {"i": ids})
    s.execute(text("DELETE FROM asset_observations WHERE asset_id = ANY(CAST(:i AS uuid[]))"), {"i": ids})
    s.execute(text("ALTER TABLE asset_observations ENABLE TRIGGER trg_asset_obs_worm"))


@pytest.fixture()
def session_rolled_back():
    shas = []
    real_put = storage.put

    def tracking_put(raw):
        out = real_put(raw)
        shas.append(out[0])
        return out
    storage.put = tracking_put
    import services.tasks.jobs as jobs
    real_submit = jobs.submit
    jobs.submit = lambda *a, **k: {"job": "stubbed-in-test"}
    with get_session() as s:
        # Guard (error log E1): code under test may commit (e.g. location edits, filing refresh). Inside this fixture a
        # commit is only a flush, so nothing a test does can reach the real database — the rollback below undoes all.
        s.commit = s.flush
        try:
            yield s
        finally:
            s.__dict__.pop("commit", None)
            s.rollback()
            storage.put, jobs.submit = real_put, real_submit
    for sha in set(shas):
        with get_session() as s:
            if not s.execute(text("SELECT 1 FROM intake_files WHERE sha256 = :h"), {"h": sha}).first():
                try:
                    os.remove(storage._path_for(sha))
                except OSError:
                    pass
