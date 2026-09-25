"""Shared fixtures for the customer data intake tests (test_intake_pipeline, test_intake_staging)."""
from __future__ import annotations

import pytest

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


