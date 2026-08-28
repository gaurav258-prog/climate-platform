"""Envelope encryption for secrets at rest (Fernet / AES-128-CBC + HMAC).

Tenant-supplied secrets like an OIDC client secret must not sit in the database in plaintext. This wraps them
with a symmetric key from the environment (`APP_ENCRYPTION_KEY`, a real Fernet key) — or, absent that, one
derived deterministically from `SECRET_KEY` so the feature works in dev without extra setup. Ciphertext carries
an `enc:v1:` marker; values without it are treated as legacy plaintext on read (a one-way migration grace), so
enabling encryption never breaks existing rows.

The key is intentionally pluggable: point `APP_ENCRYPTION_KEY` at a KMS-issued data key to graduate from
env-based to KMS-backed encryption without touching call sites.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from core.security.kms import get_key_provider, reset_provider_cache

_PREFIX = "enc:v1:"
_fernet_cache: Fernet | None = None


def _fernet() -> Fernet:
    """The Fernet built from the active key provider's data key. Cached — a KMS provider must not be
    re-hit per encrypt/decrypt; env-derived is cheap either way."""
    global _fernet_cache
    if _fernet_cache is None:
        _fernet_cache = Fernet(get_key_provider().data_key())
    return _fernet_cache


def reset_crypto_cache() -> None:
    """Drop the cached Fernet + key provider (tests / after a key/provider change)."""
    global _fernet_cache
    _fernet_cache = None
    reset_provider_cache()


def encrypt(plaintext: str | None) -> str | None:
    if not plaintext or plaintext.startswith(_PREFIX):
        return plaintext
    return _PREFIX + _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str | None) -> str | None:
    if not ciphertext or not ciphertext.startswith(_PREFIX):
        return ciphertext  # legacy plaintext (pre-encryption rows) or empty
    try:
        return _fernet().decrypt(ciphertext[len(_PREFIX):].encode()).decode()
    except InvalidToken:
        return None
