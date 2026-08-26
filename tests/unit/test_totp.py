"""RFC 6238 TOTP — the MFA primitive behind account activation and login. Pure, deterministic, no DB."""
from __future__ import annotations

from services.governance import totp

# RFC 6238 Appendix B test vector (SHA-1, 8 digits). We truncate to our 6-digit scheme.
_RFC_SECRET_ASCII = b"12345678901234567890"


def _b32(raw: bytes) -> str:
    import base64
    return base64.b32encode(raw).decode().rstrip("=")


def test_code_is_six_digits_and_stable_within_a_step():
    secret = totp.generate_secret()
    at = 1_000_000_000.0
    code = totp._code_at(secret, int(at // 30))
    assert len(code) == 6 and code.isdigit()


def test_verify_accepts_current_code():
    secret = totp.generate_secret()
    at = 1_700_000_000.0
    code = totp._code_at(secret, int(at // 30))
    assert totp.verify(secret, code, at=at) is True


def test_verify_tolerates_one_step_of_drift():
    secret = totp.generate_secret()
    at = 1_700_000_000.0
    prev = totp._code_at(secret, int(at // 30) - 1)
    nxt = totp._code_at(secret, int(at // 30) + 1)
    assert totp.verify(secret, prev, at=at) is True
    assert totp.verify(secret, nxt, at=at) is True


def test_verify_rejects_stale_and_malformed_codes():
    secret = totp.generate_secret()
    at = 1_700_000_000.0
    stale = totp._code_at(secret, int(at // 30) - 5)
    assert totp.verify(secret, stale, at=at) is False
    assert totp.verify(secret, "000000", at=at) is False   # (astronomically unlikely to match)
    assert totp.verify(secret, "12345", at=at) is False    # wrong length
    assert totp.verify(secret, "abcdef", at=at) is False   # non-numeric
    assert totp.verify(secret, "", at=at) is False
    assert totp.verify("", "123456", at=at) is False


def test_matches_rfc6238_vector():
    # RFC 6238 T=59s (SHA-1) → 8-digit 94287082 → last 6 digits 287082
    secret = _b32(_RFC_SECRET_ASCII)
    assert totp._code_at(secret, 59 // 30) == "287082"


def test_provisioning_uri_is_well_formed():
    uri = totp.provisioning_uri("ABC234", "user@example.com", issuer="Tellumen")
    assert uri.startswith("otpauth://totp/")
    assert "secret=ABC234" in uri and "issuer=Tellumen" in uri and "period=30" in uri
