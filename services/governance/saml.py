"""SAML 2.0 (SP side) — the second enterprise SSO protocol, alongside OIDC.

We are the Service Provider: a tenant's IdP authenticates the user and POSTs a signed SAML Response to our
Assertion Consumer Service (ACS). The security rests entirely on validating that Response:
  • the XML-DSig signature verifies against the IdP's configured certificate (real enveloped-signature
    verification via signxml — never accept an unsigned assertion),
  • the audience matches us, the assertion is inside its validity window, and the recipient is our ACS.

`validate_saml_response` is a pure function so it is unit-testable against a self-signed IdP cert without a
live IdP; the live redirect/POST round-trip activates once a tenant supplies a real IdP config.
"""
from __future__ import annotations

import base64
import uuid
import zlib
from datetime import datetime, timezone
from urllib.parse import urlencode

from lxml import etree
from signxml import XMLVerifier

# hardened parser — no entity expansion, no DTD, no network: blocks XXE / billion-laughs on untrusted IdP XML
_SAFE_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, dtd_validation=False)


def safe_fromstring(raw: bytes):
    return etree.fromstring(raw, parser=_SAFE_PARSER)

from core.config import settings

NS = {
    "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
    "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
    "md": "urn:oasis:names:tc:SAML:2.0:metadata",
}
_EMAIL_ATTRS = {"email", "emailaddress", "mail",
                "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"}
_NAME_ATTRS = {"name", "displayname", "cn",
               "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name"}


class SamlError(ValueError):
    """A client-facing SAML configuration or assertion-validation failure."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def sp_entity_id() -> str:
    return f"{settings.APP_BASE_URL.rstrip('/')}/sp"


def acs_url() -> str:
    return f"{settings.APP_BASE_URL.rstrip('/')}/v1/sso/saml/acs"


# ── SP-initiated login (AuthnRequest over HTTP-Redirect binding) ─────────────
def build_authn_request(*, idp_sso_url: str, relay_state: str) -> str:
    """Build an AuthnRequest and return the IdP redirect URL (deflated + base64 SAMLRequest, standard binding)."""
    req_id = "_" + uuid.uuid4().hex
    issued = _now().strftime("%Y-%m-%dT%H:%M:%SZ")
    xml = (
        f'<samlp:AuthnRequest xmlns:samlp="{NS["samlp"]}" xmlns:saml="{NS["saml"]}" '
        f'ID="{req_id}" Version="2.0" IssueInstant="{issued}" Destination="{idp_sso_url}" '
        f'AssertionConsumerServiceURL="{acs_url()}" '
        f'ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">'
        f'<saml:Issuer>{sp_entity_id()}</saml:Issuer>'
        f'</samlp:AuthnRequest>'
    )
    deflated = zlib.compress(xml.encode())[2:-4]  # raw DEFLATE (strip zlib header/checksum)
    params = urlencode({"SAMLRequest": base64.b64encode(deflated).decode(), "RelayState": relay_state})
    sep = "&" if "?" in idp_sso_url else "?"
    return f"{idp_sso_url}{sep}{params}"


# ── Response validation (the security-critical core; pure + testable) ────────
def _pem(cert: str) -> bytes:
    cert = cert.strip()
    if "BEGIN CERTIFICATE" in cert:
        return cert.encode()
    body = "".join(cert.split())
    lines = "\n".join(body[i:i + 64] for i in range(0, len(body), 64))
    return f"-----BEGIN CERTIFICATE-----\n{lines}\n-----END CERTIFICATE-----\n".encode()


def _parse_dt(value: str) -> datetime:
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    return datetime.fromisoformat(v)


def validate_saml_response(saml_response_b64: str, *, sp_entity_id: str, sp_acs_url: str | None,
                           idp_cert: str, leeway_seconds: int = 60, at: datetime | None = None) -> dict:
    """Verify a base64 SAML Response and return {email, name, name_id}. Raises SamlError on any failure."""
    try:
        raw = base64.b64decode(saml_response_b64)
    except Exception as e:  # noqa: BLE001
        raise SamlError("SAMLResponse is not valid base64") from e
    try:
        doc = safe_fromstring(raw)
    except Exception as e:  # noqa: BLE001
        raise SamlError("SAMLResponse is not well-formed XML") from e

    # 1. signature — the whole trust anchor. signxml verifies enveloped XML-DSig against the IdP cert.
    try:
        verified = XMLVerifier().verify(doc, x509_cert=_pem(idp_cert).decode()).signed_xml
    except Exception as e:  # noqa: BLE001 — any verification failure is a hard reject
        raise SamlError(f"SAML signature validation failed: {e}") from e

    # signxml returns the signed subtree; re-locate the assertion from whichever element was signed
    root = verified
    assertion = root if root.tag == f'{{{NS["saml"]}}}Assertion' else root.find(".//saml:Assertion", NS)
    if assertion is None:
        # the Response (not the Assertion) was signed — trust it and read the assertion from the full doc
        assertion = doc.find(".//saml:Assertion", NS)
    if assertion is None:
        raise SamlError("no SAML assertion found")

    now = at or _now()

    # 2. audience — the assertion must be intended for us
    conditions = assertion.find("saml:Conditions", NS)
    if conditions is not None:
        _check_window(conditions.get("NotBefore"), conditions.get("NotOnOrAfter"), now, leeway_seconds)
        audiences = [a.text for a in assertion.findall(".//saml:AudienceRestriction/saml:Audience", NS)]
        if audiences and sp_entity_id not in audiences:
            raise SamlError("SAML audience does not match this service provider")

    # 3. subject confirmation window + recipient (when present)
    scd = assertion.find(".//saml:Subject/saml:SubjectConfirmation/saml:SubjectConfirmationData", NS)
    if scd is not None:
        _check_window(None, scd.get("NotOnOrAfter"), now, leeway_seconds)
        recipient = scd.get("Recipient")
        if recipient and sp_acs_url and recipient.rstrip("/") != sp_acs_url.rstrip("/"):
            raise SamlError("SAML recipient does not match the ACS URL")

    # 4. identity — NameID (usually the email) + attribute fallbacks
    name_id_el = assertion.find(".//saml:Subject/saml:NameID", NS)
    name_id = (name_id_el.text or "").strip() if name_id_el is not None else None
    attrs = _attributes(assertion)
    email = None
    if name_id and "@" in name_id:
        email = name_id
    for key in _EMAIL_ATTRS:
        if not email and attrs.get(key):
            email = attrs[key]
    if not email:
        raise SamlError("the SAML assertion did not carry an email (NameID or an email attribute)")
    name = next((attrs[k] for k in _NAME_ATTRS if attrs.get(k)), None)
    return {"email": email.strip().lower(), "name": name, "name_id": name_id}


def _check_window(not_before: str | None, not_on_or_after: str | None, now: datetime, leeway: int) -> None:
    from datetime import timedelta
    if not_before:
        if now + timedelta(seconds=leeway) < _parse_dt(not_before):
            raise SamlError("the SAML assertion is not yet valid")
    if not_on_or_after:
        if now - timedelta(seconds=leeway) >= _parse_dt(not_on_or_after):
            raise SamlError("the SAML assertion has expired")


def _attributes(assertion) -> dict:
    out: dict[str, str] = {}
    for attr in assertion.findall(".//saml:AttributeStatement/saml:Attribute", NS):
        key = (attr.get("Name") or attr.get("FriendlyName") or "").strip().lower()
        val = attr.find("saml:AttributeValue", NS)
        if key and val is not None and val.text:
            out[key] = val.text.strip()
    return out


# ── SP metadata (hand to the IdP to configure the connection) ────────────────
def sp_metadata_xml() -> str:
    return (
        f'<?xml version="1.0"?>'
        f'<md:EntityDescriptor xmlns:md="{NS["md"]}" entityID="{sp_entity_id()}">'
        f'<md:SPSSODescriptor AuthnRequestsSigned="false" WantAssertionsSigned="true" '
        f'protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">'
        f'<md:NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress</md:NameIDFormat>'
        f'<md:AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" '
        f'Location="{acs_url()}" index="0" isDefault="true"/>'
        f'</md:SPSSODescriptor></md:EntityDescriptor>'
    )


def canonical_xml(el) -> bytes:
    return etree.tostring(el, method="c14n")
