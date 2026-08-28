"""Bootstrap a KMS-wrapped data key for secret-at-rest encryption.

Generates a fresh Fernet data key, asks the configured KMS (KMS_PROVIDER + KMS_KEY_ID) to encrypt it, and
prints the base64 blob to store as KMS_ENCRYPTED_DATA_KEY. The plaintext data key is never written anywhere —
it only ever lives in memory after the KMS decrypts it at runtime (see core/security/kms.py).

Prereqs: pip install -e ".[kms]"; KMS_PROVIDER=aws|gcp, KMS_KEY_ID set, and cloud credentials available.

    KMS_PROVIDER=aws KMS_KEY_ID=arn:aws:kms:...:key/xxxx python -m scripts.kms_wrap_data_key
"""
from __future__ import annotations

import base64
import sys

from cryptography.fernet import Fernet

from core.config import settings
from core.security.kms import AwsKmsBackend, GcpKmsBackend


def main() -> int:
    kind = (settings.KMS_PROVIDER or "").lower()
    backend = {"aws": AwsKmsBackend, "gcp": GcpKmsBackend}.get(kind)
    if not backend:
        print("Set KMS_PROVIDER=aws|gcp (and KMS_KEY_ID) first.", file=sys.stderr)
        return 2
    data_key = Fernet.generate_key()                 # the DEK — a valid Fernet key
    wrapped = backend().encrypt(data_key)            # KMS encrypts it with the KEK
    blob = base64.b64encode(wrapped).decode()
    print("# Store this as KMS_ENCRYPTED_DATA_KEY (the plaintext data key is intentionally not shown):")
    print(f"KMS_ENCRYPTED_DATA_KEY={blob}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
