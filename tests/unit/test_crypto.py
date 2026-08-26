"""Envelope encryption for secrets at rest — round-trip, tamper, and legacy-plaintext grace."""
from __future__ import annotations

from core.security import crypto


def test_roundtrip():
    ct = crypto.encrypt("super-secret-value")
    assert ct != "super-secret-value"
    assert ct.startswith("enc:v1:")
    assert crypto.decrypt(ct) == "super-secret-value"


def test_legacy_plaintext_passes_through_on_read():
    # a value written before encryption was enabled has no marker — returned as-is
    assert crypto.decrypt("legacy-plaintext") == "legacy-plaintext"


def test_double_encrypt_is_idempotent():
    ct = crypto.encrypt("x")
    assert crypto.encrypt(ct) == ct   # already-encrypted values aren't wrapped twice


def test_empty_values():
    assert crypto.encrypt(None) is None
    assert crypto.encrypt("") == ""
    assert crypto.decrypt(None) is None


def test_tampered_ciphertext_returns_none():
    ct = crypto.encrypt("secret")
    tampered = ct[:-4] + "AAAA"
    assert crypto.decrypt(tampered) is None
