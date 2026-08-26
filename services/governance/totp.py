"""RFC 6238 TOTP (time-based one-time password) on the standard library only.

We enforce MFA by default for a platform holding regulated financial/climate data, and the deployment can't
assume a third-party OTP package is installed — so this implements the standard SHA-1 / 6-digit / 30-second
authenticator scheme (compatible with Google Authenticator, Authy, 1Password, Microsoft Authenticator) with
nothing but hmac/hashlib/base64/struct. Secrets are base32, matching the otpauth:// provisioning URI.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

_DIGITS = 6
_PERIOD = 30


def generate_secret(length: int = 20) -> str:
    """A fresh base32 TOTP secret (default 160-bit, the RFC-recommended size)."""
    return base64.b32encode(secrets.token_bytes(length)).decode("ascii").rstrip("=")


def _code_at(secret_b32: str, counter: int) -> str:
    # base32 secrets are stored without padding; restore it for the decoder
    pad = "=" * (-len(secret_b32) % 8)
    key = base64.b32decode(secret_b32.upper() + pad)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(binary % (10 ** _DIGITS)).zfill(_DIGITS)


def verify(secret_b32: str, code: str, *, window: int = 1, at: float | None = None) -> bool:
    """True if `code` matches the secret within +/- `window` 30s steps (tolerates clock drift). Constant-time."""
    if not secret_b32 or not code:
        return False
    code = code.strip().replace(" ", "")
    if not code.isdigit() or len(code) != _DIGITS:
        return False
    now = int((at if at is not None else time.time()) // _PERIOD)
    for step in range(-window, window + 1):
        if hmac.compare_digest(_code_at(secret_b32, now + step), code):
            return True
    return False


def provisioning_uri(secret_b32: str, account_email: str, issuer: str = "Tellumen") -> str:
    """otpauth:// URI to render as a QR code for the authenticator app."""
    label = quote(f"{issuer}:{account_email}")
    params = f"secret={secret_b32}&issuer={quote(issuer)}&algorithm=SHA1&digits={_DIGITS}&period={_PERIOD}"
    return f"otpauth://totp/{label}?{params}"
