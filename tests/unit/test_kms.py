"""Key-provider abstraction for secret-at-rest encryption — env default + KMS envelope path.

Covers the finishable-without-cloud parts: the env-derived provider yields a usable key, encrypt/decrypt
round-trips and stays backward-compatible with the `enc:v1:` marker, and the KMS envelope logic works
against a fake backend (no real cloud needed)."""
import base64

from cryptography.fernet import Fernet

from core.security import crypto
from core.security.kms import EnvKeyProvider, KmsKeyProvider, get_key_provider, reset_provider_cache


def test_env_provider_yields_a_valid_fernet_key():
    key = EnvKeyProvider().data_key()
    Fernet(key)  # raises if not a valid Fernet key


def test_default_provider_is_env_when_kms_unset():
    reset_provider_cache()
    assert isinstance(get_key_provider(), EnvKeyProvider)


def test_encrypt_decrypt_round_trip_and_marker():
    crypto.reset_crypto_cache()
    ct = crypto.encrypt("s3cret-value")
    assert ct.startswith("enc:v1:")            # ciphertext is marked
    assert crypto.decrypt(ct) == "s3cret-value"
    # legacy plaintext (no marker) is passed through unchanged — one-way migration grace
    assert crypto.decrypt("legacy-plaintext") == "legacy-plaintext"
    assert crypto.encrypt(None) is None


class _FakeKms:
    """A stand-in KMS: 'encrypts' by prefixing, 'decrypts' by stripping — enough to exercise the envelope."""
    def encrypt(self, plaintext: bytes) -> bytes:
        return b"WRAP::" + plaintext

    def decrypt(self, blob: bytes) -> bytes:
        assert blob.startswith(b"WRAP::")
        return blob[len(b"WRAP::"):]


def test_kms_provider_envelope_unwraps_and_caches():
    dek = Fernet.generate_key()
    wrapped_b64 = base64.b64encode(b"WRAP::" + dek).decode()

    import core.security.kms as kms_mod
    prov = KmsKeyProvider(_FakeKms())
    # KMS_ENCRYPTED_DATA_KEY is read from settings; patch it for the test
    orig = kms_mod.settings.KMS_ENCRYPTED_DATA_KEY
    try:
        kms_mod.settings.KMS_ENCRYPTED_DATA_KEY = wrapped_b64
        assert prov.data_key() == dek          # envelope decrypt returns the real DEK
        # second call is cached (does not depend on settings any more)
        kms_mod.settings.KMS_ENCRYPTED_DATA_KEY = "tampered"
        assert prov.data_key() == dek
    finally:
        kms_mod.settings.KMS_ENCRYPTED_DATA_KEY = orig
