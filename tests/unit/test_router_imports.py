"""Every router group imports (E53): a failed import used to disable a whole group of routes silently — the API kept
running and answered 404. The groups are still guarded (an optional dependency must not take the API down), but in
this environment every group must load, and a failure is reported by /health."""
from __future__ import annotations


def test_every_router_group_imports():
    import api.main as m
    assert m.ROUTER_IMPORT_FAILURES == {}, m.ROUTER_IMPORT_FAILURES
    assert m.ROUTERS_AVAILABLE and m.AUTH_USER_AVAILABLE and m.ADMIN_ROUTERS_AVAILABLE
    paths = set(m.app.openapi()["paths"])                  # what a client sees
    for p in ("/v1/periods/close", "/v1/supply/sites/upload", "/v1/provided", "/v1/filings"):
        assert any(x.startswith(p) for x in paths), p
