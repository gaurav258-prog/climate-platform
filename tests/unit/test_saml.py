"""SAML 2.0 assertion validation — the security core of the SAML SSO path.

No live IdP here, so we act as one: self-signed cert, build a SAML Response, sign it with real XML-DSig
(signxml), and assert the validator accepts a good assertion and rejects tampered / wrong-audience / expired /
wrong-signer / no-email ones — the exact checks that run against Okta/Entra in production, minus the network.
"""
from __future__ import annotations

import base64
import datetime

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from lxml import etree
from signxml import XMLSigner

from services.governance import saml

SP = saml.sp_entity_id()
ACS = saml.acs_url()
IDP = "https://idp.example.com/saml"


@pytest.fixture(scope="module")
def signer():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subj = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "idp.example.com")])
    cert = (x509.CertificateBuilder().subject_name(subj).issuer_name(subj)
            .public_key(key.public_key()).serial_number(1)
            .not_valid_before(datetime.datetime(2020, 1, 1)).not_valid_after(datetime.datetime(2035, 1, 1))
            .sign(key, hashes.SHA256()))
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    return key, cert_pem


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _response_xml(*, audience=SP, email="user@corp.com", name_id=None, recipient=ACS,
                  not_before=None, not_after=None):
    now = datetime.datetime.utcnow()
    nb = _iso(not_before or now - datetime.timedelta(minutes=5))
    na = _iso(not_after or now + datetime.timedelta(minutes=5))
    nameid = name_id if name_id is not None else email
    return (
        f'<samlp:Response xmlns:samlp="{saml.NS["samlp"]}" xmlns:saml="{saml.NS["saml"]}" '
        f'ID="_resp1" Version="2.0" IssueInstant="{_iso(now)}">'
        f'<saml:Issuer>{IDP}</saml:Issuer>'
        f'<saml:Assertion ID="_a1" Version="2.0" IssueInstant="{_iso(now)}">'
        f'<saml:Issuer>{IDP}</saml:Issuer>'
        f'<saml:Subject><saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">{nameid}</saml:NameID>'
        f'<saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">'
        f'<saml:SubjectConfirmationData Recipient="{recipient}" NotOnOrAfter="{na}"/>'
        f'</saml:SubjectConfirmation></saml:Subject>'
        f'<saml:Conditions NotBefore="{nb}" NotOnOrAfter="{na}">'
        f'<saml:AudienceRestriction><saml:Audience>{audience}</saml:Audience></saml:AudienceRestriction>'
        f'</saml:Conditions>'
        f'<saml:AttributeStatement>'
        f'<saml:Attribute Name="name"><saml:AttributeValue>Test User</saml:AttributeValue></saml:Attribute>'
        f'</saml:AttributeStatement>'
        f'</saml:Assertion></samlp:Response>'
    )


def _signed_b64(signer, xml: str) -> str:
    key, cert_pem = signer
    root = etree.fromstring(xml.encode())
    signed = XMLSigner(signature_algorithm="rsa-sha256", digest_algorithm="sha256").sign(root, key=key, cert=cert_pem)
    return base64.b64encode(etree.tostring(signed)).decode()


def test_valid_assertion_is_accepted(signer):
    _key, cert = signer
    claims = saml.validate_saml_response(_signed_b64(signer, _response_xml()),
                                         sp_entity_id=SP, sp_acs_url=ACS, idp_cert=cert)
    assert claims["email"] == "user@corp.com"
    assert claims["name"] == "Test User"


def test_tampered_assertion_is_rejected(signer):
    _key, cert = signer
    b64 = _signed_b64(signer, _response_xml(email="user@corp.com"))
    raw = base64.b64decode(b64).replace(b"user@corp.com", b"attacker@evil.com")
    with pytest.raises(saml.SamlError):
        saml.validate_saml_response(base64.b64encode(raw).decode(), sp_entity_id=SP, sp_acs_url=ACS, idp_cert=cert)


def test_wrong_audience_is_rejected(signer):
    _key, cert = signer
    b64 = _signed_b64(signer, _response_xml(audience="https://someone-else/sp"))
    with pytest.raises(saml.SamlError):
        saml.validate_saml_response(b64, sp_entity_id=SP, sp_acs_url=ACS, idp_cert=cert)


def test_expired_assertion_is_rejected(signer):
    _key, cert = signer
    past = datetime.datetime.utcnow() - datetime.timedelta(hours=2)
    b64 = _signed_b64(signer, _response_xml(not_before=past - datetime.timedelta(minutes=5), not_after=past))
    with pytest.raises(saml.SamlError):
        saml.validate_saml_response(b64, sp_entity_id=SP, sp_acs_url=ACS, idp_cert=cert)


def test_response_signed_by_a_different_key_is_rejected(signer):
    b64 = _signed_b64(signer, _response_xml())
    # a DIFFERENT cert is configured on the tenant than the one that actually signed
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subj = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "other")])
    other_cert = (x509.CertificateBuilder().subject_name(subj).issuer_name(subj)
                  .public_key(other.public_key()).serial_number(2)
                  .not_valid_before(datetime.datetime(2020, 1, 1)).not_valid_after(datetime.datetime(2035, 1, 1))
                  .sign(other, hashes.SHA256())).public_bytes(serialization.Encoding.PEM).decode()
    with pytest.raises(saml.SamlError):
        saml.validate_saml_response(b64, sp_entity_id=SP, sp_acs_url=ACS, idp_cert=other_cert)


def test_assertion_without_email_is_rejected(signer):
    _key, cert = signer
    b64 = _signed_b64(signer, _response_xml(email="not-an-email", name_id="not-an-email"))
    with pytest.raises(saml.SamlError):
        saml.validate_saml_response(b64, sp_entity_id=SP, sp_acs_url=ACS, idp_cert=cert)


def test_authn_request_builds_a_redirect_with_deflated_samlrequest():
    url = saml.build_authn_request(idp_sso_url="https://idp.example.com/sso", relay_state="org-123")
    assert url.startswith("https://idp.example.com/sso?")
    assert "SAMLRequest=" in url and "RelayState=org-123" in url
