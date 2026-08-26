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

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from core.config import settings

_PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    raw = (settings.APP_ENCRYPTION_KEY or "").strip()
    if raw:
        # accept either a proper 44-char urlsafe-b64 Fernet key, or any passphrase (hashed to one)
        try:
            Fernet(raw.encode())
            return Fernet(raw.encode())
        except Exception:  # noqa: BLE001
            key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
            return Fernet(key)
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


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
