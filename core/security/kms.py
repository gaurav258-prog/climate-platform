"""Key providers for secret-at-rest encryption — env-derived by default, KMS-backed in production.

The app encrypts secrets with a symmetric **data key** (a Fernet key). Where that data key comes from is
pluggable:

  • EnvKeyProvider  — the data key is APP_ENCRYPTION_KEY (or derived from SECRET_KEY). Zero-setup default for
                      dev/test. The key material sits in the environment.
  • KmsKeyProvider  — envelope encryption: a KMS holds the *key-encryption key* (KEK); we store only the
                      **KMS-encrypted data key** (KMS_ENCRYPTED_DATA_KEY). At startup the KMS decrypts it once
                      into the plaintext data key, which is cached in memory. The raw key never lives in config
                      or the DB, and the KEK can be rotated in the KMS without re-encrypting any row.

Selected by `settings.KMS_PROVIDER` (""/none → env, "aws"/"gcp" → KMS). Cloud SDKs are imported lazily, so the
KMS path is a deployment concern, never a hard dependency. Bootstrap a wrapped data key with
`scripts/kms_wrap_data_key.py`.
"""
from __future__ import annotations

import base64
import hashlib
from typing import Optional, Protocol

from cryptography.fernet import Fernet

from core.config import settings


class KeyProvider(Protocol):
    def data_key(self) -> bytes:
        """Return a valid Fernet key (44-char urlsafe-b64 bytes)."""
        ...


class EnvKeyProvider:
    """Data key from APP_ENCRYPTION_KEY, or deterministically derived from SECRET_KEY (dev default)."""

    def data_key(self) -> bytes:
        raw = (settings.APP_ENCRYPTION_KEY or "").strip()
        if raw:
            try:
                Fernet(raw.encode())        # already a proper Fernet key?
                return raw.encode()
            except Exception:  # noqa: BLE001 — treat any passphrase as key material
                return base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
        return base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())


class _KmsBackend(Protocol):
    def decrypt(self, blob: bytes) -> bytes: ...
    def encrypt(self, plaintext: bytes) -> bytes: ...


class AwsKmsBackend:
    """AWS KMS via boto3 (lazy import). encrypt/decrypt operate on the small data-key blob only."""

    def _client(self):
        import boto3  # lazy — only when the AWS path is actually used
        region = getattr(settings, "KMS_REGION", "") or None
        return boto3.client("kms", region_name=region)

    def decrypt(self, blob: bytes) -> bytes:
        return self._client().decrypt(CiphertextBlob=blob)["Plaintext"]

    def encrypt(self, plaintext: bytes) -> bytes:
        key_id = getattr(settings, "KMS_KEY_ID", "")
        if not key_id:
            raise RuntimeError("KMS_KEY_ID is required to encrypt (wrap) a data key")
        return self._client().encrypt(KeyId=key_id, Plaintext=plaintext)["CiphertextBlob"]


class GcpKmsBackend:
    """Google Cloud KMS via google-cloud-kms (lazy import). KMS_KEY_ID = the crypto-key resource name."""

    def _client(self):
        from google.cloud import kms  # lazy
        return kms.KeyManagementServiceClient()

    def decrypt(self, blob: bytes) -> bytes:
        return self._client().decrypt(request={"name": settings.KMS_KEY_ID, "ciphertext": blob}).plaintext

    def encrypt(self, plaintext: bytes) -> bytes:
        return self._client().encrypt(request={"name": settings.KMS_KEY_ID, "plaintext": plaintext}).ciphertext


class KmsKeyProvider:
    """Envelope encryption: decrypt the stored KMS-wrapped data key once, cache the plaintext data key."""

    def __init__(self, backend: _KmsBackend):
        self._backend = backend
        self._cached: Optional[bytes] = None

    def data_key(self) -> bytes:
        if self._cached is None:
            wrapped = (getattr(settings, "KMS_ENCRYPTED_DATA_KEY", "") or "").strip()
            if not wrapped:
                raise RuntimeError("KMS_ENCRYPTED_DATA_KEY is not set — run scripts/kms_wrap_data_key.py")
            key = self._backend.decrypt(base64.b64decode(wrapped))
            Fernet(key)   # validate: a decrypted data key must be a usable Fernet key
            self._cached = key
        return self._cached


_BACKENDS = {"aws": AwsKmsBackend, "gcp": GcpKmsBackend}
_provider_cache: Optional[KeyProvider] = None


def get_key_provider() -> KeyProvider:
    """Select the key provider from config; env-derived unless a KMS provider is configured. Cached."""
    global _provider_cache
    if _provider_cache is not None:
        return _provider_cache
    kind = (getattr(settings, "KMS_PROVIDER", "") or "").strip().lower()
    if kind in _BACKENDS:
        _provider_cache = KmsKeyProvider(_BACKENDS[kind]())
    else:
        _provider_cache = EnvKeyProvider()
    return _provider_cache


def reset_provider_cache() -> None:
    """Drop the cached provider (tests / after a config change)."""
    global _provider_cache
    _provider_cache = None
