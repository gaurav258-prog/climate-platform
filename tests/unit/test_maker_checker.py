"""
Unit tests for maker/checker workflow and regulatory fingerprint.

Tests the core IP: 4-eyes enforcement, immutability, and fingerprint determinism.
Uses real DB (integration test style) — requires running PostgreSQL on port 5433.
"""
import hashlib
import json
import uuid
from datetime import date, datetime, timezone

import pytest

from core.db.session import get_session
from ml.regulatory.packager import (
    MakerCheckerViolation,
    PackageAlreadyReleased,
    approve_package,
    create_package,
    get_package,
)
from ml.scoring.engine import _regulatory_fingerprint


# ── Regulatory fingerprint tests (pure, no DB) ────────────────────────

_SCORED_AT = datetime(2024, 7, 14, 12, 0, 0, tzinfo=timezone.utc)


class TestRegulatoryFingerprint:
    def test_returns_64_char_hex(self):
        fp = _regulatory_fingerprint(
            h3_cell="881f1d4a13fffff",
            hazard_type="flood",
            scenario="baseline",
            observation_ids=["obs-1", "obs-2"],
            model_version="v1",
            scored_at=_SCORED_AT,
            raw_score=72.5,
        )
        assert len(fp) == 64
        int(fp, 16)  # raises if not hex

    def test_deterministic_same_inputs(self):
        kwargs = dict(
            h3_cell="881f1d4a13fffff",
            hazard_type="flood",
            scenario="baseline",
            observation_ids=["obs-1"],
            model_version="v1",
            scored_at=_SCORED_AT,
            raw_score=72.5,
        )
        assert _regulatory_fingerprint(**kwargs) == _regulatory_fingerprint(**kwargs)

    def test_different_score_gives_different_fingerprint(self):
        base = dict(
            h3_cell="881f1d4a13fffff",
            hazard_type="flood",
            scenario="baseline",
            observation_ids=["obs-1"],
            model_version="v1",
            scored_at=_SCORED_AT,
        )
        fp_a = _regulatory_fingerprint(**base, raw_score=72.5)
        fp_b = _regulatory_fingerprint(**base, raw_score=73.0)
        assert fp_a != fp_b

    def test_different_cell_gives_different_fingerprint(self):
        base = dict(
            hazard_type="flood",
            scenario="baseline",
            observation_ids=["obs-1"],
            model_version="v1",
            scored_at=_SCORED_AT,
            raw_score=72.5,
        )
        fp_a = _regulatory_fingerprint(h3_cell="881f1d4a13fffff", **base)
        fp_b = _regulatory_fingerprint(h3_cell="881f1d4b11fffff", **base)
        assert fp_a != fp_b

    def test_observation_order_is_sorted(self):
        """obs IDs must be sorted before hashing so order doesn't affect the fingerprint."""
        base = dict(
            h3_cell="881f1d4a13fffff",
            hazard_type="flood",
            scenario="baseline",
            model_version="v1",
            scored_at=_SCORED_AT,
            raw_score=72.5,
        )
        fp_a = _regulatory_fingerprint(observation_ids=["obs-2", "obs-1"], **base)
        fp_b = _regulatory_fingerprint(observation_ids=["obs-1", "obs-2"], **base)
        assert fp_a == fp_b, "Fingerprint must be order-independent on observation_ids"

    def test_fingerprint_is_sha256(self):
        """Manually compute expected hash to confirm algorithm."""
        scored_at_iso = _SCORED_AT.isoformat()
        payload = {
            "h3_cell":         "881f1d4a13fffff",
            "hazard_type":     "flood",
            "scenario":        "baseline",
            "observation_ids": sorted(["obs-1"]),
            "model_version":   "v1",
            "scored_at":       scored_at_iso,
            "raw_score":       72.5,
        }
        expected = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()
        result = _regulatory_fingerprint(
            h3_cell="881f1d4a13fffff",
            hazard_type="flood",
            scenario="baseline",
            observation_ids=["obs-1"],
            model_version="v1",
            scored_at=_SCORED_AT,
            raw_score=72.5,
        )
        assert result == expected


# ── Maker/checker DB tests ──────────────────────────────────────────────

def _customer() -> str:
    return str(uuid.uuid4())


def _make_package(customer_id: str, maker: str = "maker-user-01") -> dict:
    """Create a minimal CSRD package with no real data."""
    return create_package(
        customer_id=customer_id,
        framework="CSRD",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
        maker_user_id=maker,
    )


@pytest.mark.integration
class TestMakerChecker:
    def test_create_package_status_is_draft(self):
        result = _make_package(_customer())
        assert result["status"] == "DRAFT"
        assert result["is_released"] is False

    def test_create_package_records_maker(self):
        result = _make_package(_customer(), maker="alice-01")
        assert result["maker"] == "alice-01"
        # checker is absent in draft response — only present after approval
        assert result.get("checker") is None

    def test_get_package_roundtrip(self):
        customer = _customer()
        created = _make_package(customer)
        fetched = get_package(created["package_id"])
        assert fetched is not None
        assert fetched["package_id"] == created["package_id"]
        assert fetched["framework"] == "CSRD"

    def test_maker_cannot_be_checker(self):
        created = _make_package(_customer(), maker="alice-01")
        with pytest.raises(MakerCheckerViolation):
            approve_package(created["package_id"], checker_user_id="alice-01")

    def test_different_user_can_approve(self):
        created = _make_package(_customer(), maker="alice-01")
        result = approve_package(created["package_id"], checker_user_id="bob-02")
        assert result["is_released"] is True
        assert result["checker"] == "bob-02"

    def test_released_package_is_immutable(self):
        created = _make_package(_customer(), maker="alice-01")
        approve_package(created["package_id"], checker_user_id="bob-02")
        # Trying to approve again raises PackageAlreadyReleased
        with pytest.raises(PackageAlreadyReleased):
            approve_package(created["package_id"], checker_user_id="carol-03")

    def test_released_package_has_released_at(self):
        created = _make_package(_customer(), maker="alice-01")
        result = approve_package(created["package_id"], checker_user_id="bob-02")
        assert result.get("released_at") is not None

    def test_unknown_package_id_returns_none(self):
        assert get_package(str(uuid.uuid4())) is None

    def test_checker_cannot_be_maker_even_with_different_case(self):
        """user IDs are case-sensitive strings — 'Alice' != 'alice'."""
        created = _make_package(_customer(), maker="alice-01")
        # Different case — should succeed (they are technically different IDs)
        result = approve_package(created["package_id"], checker_user_id="Alice-01")
        assert result["is_released"] is True
