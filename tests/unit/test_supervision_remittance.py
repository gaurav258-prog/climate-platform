"""Governed remittance: the pure rules — status, scoping, the watermarked/withheld render, the registry config."""
from datetime import datetime, timedelta, timezone

from services.supervision.evidence import SECTIONS, render_pdf
from services.supervision.remittance import config, scope_content, status_of
from tests.unit.test_supervision_evidence import _content

NOW = datetime(2026, 9, 9, 12, tzinfo=timezone.utc)


def _row(**kw):
    return {"revoked_at": None, "expires_at": NOW + timedelta(days=1), "max_downloads": None, "n_downloads": 0, **kw}


def test_status_precedence_revoked_expired_exhausted_active():
    assert status_of(_row(), NOW) == "active"
    assert status_of(_row(expires_at=NOW - timedelta(seconds=1)), NOW) == "expired"
    assert status_of(_row(max_downloads=2, n_downloads=2), NOW) == "exhausted"
    assert status_of(_row(max_downloads=2, n_downloads=1), NOW) == "active"
    assert status_of(_row(revoked_at=NOW, expires_at=NOW - timedelta(days=1)), NOW) == "revoked"     # revocation wins


def test_scope_keeps_identity_and_marks_the_rest_withheld():
    meta = {"reference": "X-2026-RM-0001", "purpose": "p"}
    out = scope_content(_content(), ["exposure"], meta)
    assert out["identity"]["name"] == "Test Bank" and out["exposure"]["note"] and out["remittance"] == meta
    for key in SECTIONS:
        if key not in ("identity", "exposure"):
            assert out[key] == {"withheld": True, "reason": "Not included in this remittance."}
    assert out["pack"]["sections_included"] == ["exposure"]


def test_render_withheld_and_watermarked_differs_from_full():
    full = render_pdf(_content())
    part = render_pdf(_content(), sections=["identity", "exposure"], watermark="REMITTED X-2026-RM-0001 · not for onward distribution", notice="Remitted to a college.")
    assert part[:5] == b"%PDF-" and part != full


def test_registry_config_is_complete_and_sector_free():
    c = config()
    assert set(c["recipient_kinds"]) >= {"authority", "college", "committee"}
    assert 1 <= c["default_expiry_days"] <= c["max_expiry_days"]
    assert "{reference}" in c["watermark_format"] and "{expires}" in c["watermark_format"]
    assert not any(w in c["notice"].lower() for w in ("bank", "insurer", "credit institution"))
