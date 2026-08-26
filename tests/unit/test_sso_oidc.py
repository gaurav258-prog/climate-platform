"""OIDC ID-token validation — the security-critical core of enterprise SSO.

We can't reach a live IdP here, so we mint our own RSA keypair, publish it as a JWKS, sign ID tokens with it,
and assert the validator accepts a good token and rejects tampered / wrong-audience / expired / wrong-issuer
ones. This is exactly the check that runs against Okta/Entra in production, minus the network.
"""
from __future__ import annotations

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from services.governance import sso

ISSUER = "https://idp.example.com"
CLIENT_ID = "tellumen-client-123"


@pytest.fixture(scope="module")
def keypair():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(priv.public_key()))
    jwk.update({"kid": "test-key", "alg": "RS256", "use": "sig"})
    return priv, jwk


def _token(priv, *, iss=ISSUER, aud=CLIENT_ID, email="user@corp.com", exp_delta=3600, kid="test-key", **extra):
    now = int(time.time())
    claims = {"iss": iss, "aud": aud, "sub": "idp-sub-1", "email": email, "name": "Test User",
              "iat": now, "exp": now + exp_delta, **extra}
    return jwt.encode(claims, priv, algorithm="RS256", headers={"kid": kid})


def test_valid_token_is_accepted(keypair):
    priv, jwk = keypair
    claims = sso.validate_id_token(_token(priv), issuer=ISSUER, client_id=CLIENT_ID, jwks=[jwk])
    assert claims["email"] == "user@corp.com"
    assert claims["sub"] == "idp-sub-1"


def test_wrong_audience_is_rejected(keypair):
    priv, jwk = keypair
    with pytest.raises(sso.SsoError):
        sso.validate_id_token(_token(priv, aud="some-other-client"), issuer=ISSUER, client_id=CLIENT_ID, jwks=[jwk])


def test_wrong_issuer_is_rejected(keypair):
    priv, jwk = keypair
    with pytest.raises(sso.SsoError):
        sso.validate_id_token(_token(priv, iss="https://evil.example.com"), issuer=ISSUER, client_id=CLIENT_ID, jwks=[jwk])


def test_expired_token_is_rejected(keypair):
    priv, jwk = keypair
    with pytest.raises(sso.SsoError):
        sso.validate_id_token(_token(priv, exp_delta=-3600), issuer=ISSUER, client_id=CLIENT_ID, jwks=[jwk])


def test_token_signed_by_a_different_key_is_rejected(keypair):
    _priv, jwk = keypair
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = _token(attacker)  # signed by a key NOT in the published JWKS
    with pytest.raises(sso.SsoError):
        sso.validate_id_token(forged, issuer=ISSUER, client_id=CLIENT_ID, jwks=[jwk])


def test_token_without_email_is_rejected(keypair):
    priv, jwk = keypair
    now = int(time.time())
    no_email = jwt.encode({"iss": ISSUER, "aud": CLIENT_ID, "sub": "s", "iat": now, "exp": now + 600},
                          priv, algorithm="RS256", headers={"kid": "test-key"})
    with pytest.raises(sso.SsoError):
        sso.validate_id_token(no_email, issuer=ISSUER, client_id=CLIENT_ID, jwks=[jwk])
