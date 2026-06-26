"""
API integration tests using FastAPI TestClient.

Tests the full HTTP contract — auth, routing, error shapes, and response schemas.
Requires running PostgreSQL (port 5433) — marked with @pytest.mark.integration.

All tests share a single customer UUID and API key created once via fixture.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app, raise_server_exceptions=False)


# ── Fixtures ───────────────────────────────────────────────────────────

CUSTOMER_ID = str(uuid.uuid4())


@pytest.fixture(scope="module")
def api_key() -> str:
    """Bootstrap a real API key for CUSTOMER_ID — used by all auth'd tests."""
    resp = client.post("/v1/auth/keys", json={
        "name":        "test-key",
        "customer_id": CUSTOMER_ID,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["raw_key"]


@pytest.fixture()
def auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


# ── Health ─────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── Auth endpoints ─────────────────────────────────────────────────────

@pytest.mark.integration
class TestAuth:
    def test_bootstrap_creates_key(self):
        cust = str(uuid.uuid4())
        resp = client.post("/v1/auth/keys", json={"name": "k1", "customer_id": cust})
        assert resp.status_code == 201
        data = resp.json()
        assert data["raw_key"].startswith("cp_live_")
        assert len(data["raw_key"]) == 40
        assert data["customer_id"] == cust
        assert "raw_key" in data

    def test_bootstrap_missing_customer_id_returns_422(self):
        resp = client.post("/v1/auth/keys", json={"name": "k"})
        assert resp.status_code == 422

    def test_bootstrap_invalid_customer_id_returns_422(self):
        resp = client.post("/v1/auth/keys", json={
            "name": "k", "customer_id": "not-a-uuid"
        })
        assert resp.status_code == 422

    def test_list_keys_requires_auth(self):
        resp = client.get("/v1/auth/keys")
        assert resp.status_code == 401

    def test_list_keys_returns_own_keys(self, api_key, auth):
        resp = client.get("/v1/auth/keys", headers=auth)
        assert resp.status_code == 200
        keys = resp.json()
        assert isinstance(keys, list)
        assert all(k["customer_id"] == CUSTOMER_ID
                   for k in keys
                   if "customer_id" in k)

    def test_revoke_key(self):
        cust = str(uuid.uuid4())
        create = client.post("/v1/auth/keys", json={"name": "temp", "customer_id": cust})
        raw    = create.json()["raw_key"]
        key_id = create.json()["key_id"]

        # Key works before revoke
        assert client.get("/v1/auth/keys",
                          headers={"Authorization": f"Bearer {raw}"}).status_code == 200

        # Revoke
        rev = client.delete(f"/v1/auth/keys/{key_id}",
                            headers={"Authorization": f"Bearer {raw}"})
        assert rev.status_code == 200
        assert rev.json()["revoked"] is True

        # Key no longer works
        assert client.get("/v1/auth/keys",
                          headers={"Authorization": f"Bearer {raw}"}).status_code == 401

    def test_revoke_nonexistent_key_returns_404(self, auth):
        resp = client.delete(f"/v1/auth/keys/{uuid.uuid4()}", headers=auth)
        assert resp.status_code == 404

    def test_second_key_via_auth(self, api_key, auth):
        resp = client.post("/v1/auth/keys",
                           json={"name": "second"},
                           headers=auth)
        assert resp.status_code == 201
        assert resp.json()["customer_id"] == CUSTOMER_ID


# ── Auth rejection (all protected endpoints) ───────────────────────────

@pytest.mark.integration
class TestAuthRejection:
    PROTECTED = [
        ("GET",  "/v1/scores/portfolio"),
        ("GET",  "/v1/scores/portfolio/alerts"),
        ("GET",  "/v1/scores/compound"),
        ("GET",  "/v1/locations"),
        ("POST", "/v1/locations"),
        ("GET",  "/v1/packages"),
        ("POST", "/v1/packages"),
    ]

    def test_no_header_returns_401(self):
        for method, path in self.PROTECTED:
            resp = client.request(method, path)
            assert resp.status_code == 401, f"{method} {path} should be 401 without auth"

    def test_bad_token_returns_401(self):
        headers = {"Authorization": "Bearer cp_live_bad"}
        for method, path in self.PROTECTED:
            resp = client.request(method, path, headers=headers)
            assert resp.status_code == 401, f"{method} {path} should be 401 with bad token"


# ── Scores ─────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestScores:
    def test_portfolio_returns_list(self, auth):
        resp = client.get("/v1/scores/portfolio", headers=auth)
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "scores" in data
        assert isinstance(data["scores"], list)

    def test_portfolio_alerts_returns_list(self, auth):
        resp = client.get("/v1/scores/portfolio/alerts", headers=auth)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_compound_events_returns_list(self, auth):
        resp = client.get("/v1/scores/compound", headers=auth)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_cell_scores_valid_h3(self, auth):
        resp = client.get("/v1/scores/cell/8928308280fffff", headers=auth)
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "scores" in data

    def test_cell_history_requires_hazard_type(self, auth):
        resp = client.get("/v1/scores/cell/8928308280fffff/history", headers=auth)
        assert resp.status_code == 422  # hazard_type is required

    def test_cell_history_valid_h3(self, auth):
        resp = client.get(
            "/v1/scores/cell/8928308280fffff/history?hazard_type=flood", headers=auth
        )
        assert resp.status_code == 200

    def test_portfolio_accepts_scenario_filter(self, auth):
        resp = client.get("/v1/scores/portfolio?scenario=orderly", headers=auth)
        assert resp.status_code == 200

    def test_portfolio_accepts_pagination(self, auth):
        resp = client.get("/v1/scores/portfolio?limit=10&offset=0", headers=auth)
        assert resp.status_code == 200


# ── Locations ──────────────────────────────────────────────────────────

@pytest.mark.integration
class TestLocations:
    def test_list_locations_returns_envelope(self, auth):
        resp = client.get("/v1/locations", headers=auth)
        assert resp.status_code == 200
        data = resp.json()
        assert "locations" in data
        assert "total" in data

    def test_register_location(self, auth):
        resp = client.post("/v1/locations", headers=auth, json={
            "name":      "Frankfurt HQ",
            "latitude":  50.1109,
            "longitude": 8.6821,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "location_id" in data
        assert "h3_cell_r8" in data
        assert len(data["h3_cell_r8"]) == 15   # H3 res 8 cell

    def test_register_location_invalid_lat(self, auth):
        resp = client.post("/v1/locations", headers=auth, json={
            "name": "Bad", "latitude": 999, "longitude": 0
        })
        assert resp.status_code == 422

    def test_delete_location(self, auth):
        create = client.post("/v1/locations", headers=auth, json={
            "name": "Temp", "latitude": 48.8, "longitude": 2.3
        })
        assert create.status_code == 201
        loc_id = create.json()["location_id"]

        delete = client.delete(f"/v1/locations/{loc_id}", headers=auth)
        assert delete.status_code in (200, 204)


# ── Meta ───────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestMeta:
    def test_hazards(self):
        resp = client.get("/v1/meta/hazards")
        assert resp.status_code == 200
        ids = [h["id"] for h in resp.json()["hazards"]]
        assert "flood" in ids
        assert "wildfire" in ids
        assert "heat_acute" in ids

    def test_scenarios(self):
        resp = client.get("/v1/meta/scenarios")
        assert resp.status_code == 200
        ids = [s["id"] for s in resp.json()["scenarios"]]
        assert "baseline" in ids
        assert "hot_house" in ids

    def test_frameworks(self):
        resp = client.get("/v1/meta/frameworks")
        assert resp.status_code == 200
        ids = [f["id"] for f in resp.json()["frameworks"]]
        assert "ECB" in ids
        assert "CSRD" in ids


# ── Packages ───────────────────────────────────────────────────────────

@pytest.mark.integration
class TestPackages:
    def test_list_packages_empty(self, auth):
        resp = client.get("/v1/packages", headers=auth)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_package(self, auth):
        resp = client.post("/v1/packages", headers=auth, json={
            "framework":    "CSRD",
            "period_start": "2024-01-01",
            "period_end":   "2024-12-31",
            "maker_user_id": "alice-01",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "DRAFT"
        assert "package_id" in data

    def test_maker_checker_violation_returns_422(self, auth):
        create = client.post("/v1/packages", headers=auth, json={
            "framework":    "CSRD",
            "period_start": "2024-01-01",
            "period_end":   "2024-12-31",
            "maker_user_id": "alice-01",
        })
        assert create.status_code == 201
        pkg_id = create.json()["package_id"]

        approve = client.post(f"/v1/packages/{pkg_id}/approve",
                              headers=auth,
                              json={"checker_user_id": "alice-01"})
        assert approve.status_code == 422
        assert approve.json()["detail"]["error"] == "maker_checker_violation"

    def test_approve_package(self, auth):
        create = client.post("/v1/packages", headers=auth, json={
            "framework":    "ECB",
            "period_start": "2024-01-01",
            "period_end":   "2024-12-31",
            "maker_user_id": "alice-01",
        })
        pkg_id = create.json()["package_id"]

        approve = client.post(f"/v1/packages/{pkg_id}/approve",
                              headers=auth,
                              json={"checker_user_id": "bob-02"})
        assert approve.status_code == 200
        data = approve.json()
        assert data.get("status") == "RELEASED" or data.get("immutable") is True

    def test_xbrl_only_for_csrd(self, auth):
        create = client.post("/v1/packages", headers=auth, json={
            "framework":    "ECB",
            "period_start": "2024-01-01",
            "period_end":   "2024-12-31",
            "maker_user_id": "alice-01",
        })
        pkg_id = create.json()["package_id"]
        resp = client.get(f"/v1/packages/{pkg_id}/xbrl?lei=5493001KJTIIGC8Y1R12",
                          headers=auth)
        assert resp.status_code == 422
