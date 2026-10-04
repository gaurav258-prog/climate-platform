"""The routes that answer without a signed-in user — each reviewed, each with its reason (error log E24).

Every other route must carry an authentication dependency (a user session, an API key, an ingest token, a permission)
or the sector tenant resolver (a caller without a session sees only that sector's public demo organisation). A route
that takes a record id and serves anonymous callers must check the record belongs to the caller's organisation
(api.deps.own_or_404). tests/unit/test_route_security.py fails the build for any route outside these rules.
"""
from __future__ import annotations

PUBLIC_ROUTES: dict[str, str] = {
    # service health and meta
    "GET /": "service banner",
    "GET /health": "liveness / readiness; reports the running code version",
    "GET /health/schedules": "scheduler liveness",
    "GET /info": "service description",
    "GET /metrics": "Prometheus scrape endpoint (network-restricted in deployment)",
    "GET /v1/meta/frameworks": "public list of supported frameworks",
    "GET /v1/meta/hazards": "public list of hazards",
    "GET /v1/meta/scenarios": "public list of scenarios",
    # signing in, recovering access, onboarding — each validates its own token or credentials
    "POST /v1/auth/login": "sign-in",
    "POST /v1/auth/refresh": "refresh-token exchange (validates the refresh token)",
    "POST /v1/auth/password/forgot": "reset request; never reveals whether an email exists",
    "GET /v1/auth/password/reset/{token}": "validates a one-time reset token",
    "POST /v1/auth/password/reset/{token}": "sets a password with a one-time reset token",
    "POST /v1/auth/passkey/login/options": "passkey sign-in challenge",
    "POST /v1/auth/passkey/login/verify": "passkey sign-in verification",
    "POST /v1/auth/keys": "API key creation: operator bootstrap secret or an existing key, checked inside",
    "POST /v1/signup": "free-trial sign-up",
    "GET /v1/sso/discover": "SSO provider discovery by email domain",
    "GET /v1/sso/login": "SSO redirect",
    "GET /v1/sso/callback": "SSO callback (validates the provider's response)",
    "GET /v1/sso/saml/metadata": "SAML service-provider metadata",
    "POST /v1/sso/saml/acs": "SAML assertion consumer (validates the signed assertion)",
    "GET /v1/sso/saml/logout": "SAML logout",
    "GET /v1/onboarding/form/{token}": "client intake form, one-time token checked inside",
    "PUT /v1/onboarding/form/{token}": "client intake form, one-time token checked inside",
    "POST /v1/onboarding/form/{token}/documents": "client intake documents, one-time token checked inside",
    "GET /v1/onboarding/activate/{token}": "account activation, one-time token checked inside",
    "POST /v1/onboarding/activate/{token}/password": "account activation, one-time token checked inside",
    "POST /v1/onboarding/activate/{token}/mfa/begin": "account activation, one-time token checked inside",
    "POST /v1/onboarding/activate/{token}/mfa/confirm": "account activation, one-time token checked inside",
    # machine interfaces with their own credentials
    "GET /scim/v2/ServiceProviderConfig": "SCIM discovery (public by the SCIM standard)",
    "GET /v1/packages/{package_id}": "API-key checked inside (401 without)",
    "GET /v1/packages/{package_id}/xbrl": "API-key checked inside (401 without)",
    "POST /v1/packages/{package_id}/approve": "API-key checked inside (401 without); 4-eyes enforced",
    # time-limited share links — the token is the credential
    "GET /v1/assurance/{token}": "auditor share link, signed expiring token",
    "GET /v1/assurance/{token}/download.zip": "auditor share link, signed expiring token",
    "GET /v1/remit/{token}": "regulator remittance link, signed expiring token",
    "GET /v1/remit/{token}/download.{fmt}": "regulator remittance link, signed expiring token",
    # public reference and methodology — no customer data
    "GET /v1/lookup/score": "public any-address climate lookup (product feature, no customer data)",
    "GET /v1/lookup/score/{lookup_id}": "public any-address climate lookup result",
    "GET /v1/scores/cell/{h3_cell}": "public hazard score of a map cell",
    "GET /v1/scores/cell/{h3_cell}/history": "public hazard score history of a map cell",
    "GET /v1/platform/geo": "public map layers",
    "GET /v1/platform/models": "public model cards",
    "GET /v1/platform/seismic-events": "public seismic event feed",
    "GET /v1/platform/verification": "public forecast verification",
    "GET /v1/supply/commodities": "public commodity reference list",
    "GET /v1/supply/validation": "public model validation results",
    "GET /v1/vendor/profiles": "public vendor column-mapping profiles",
    "GET /v1/voluntary-pai/catalog": "public list of adoptable SFDR indicators (from the regulation)",
    # retired exports — answer 410 with the reason, serve no data
    "GET /v1/funds/{fund_id}/sfdr-statement.xbrl": "retired SFDR PAI XBRL (E113): 410, no data",
    "GET /v1/funds/{fund_id}/sfdr-statement.ixbrl": "retired SFDR PAI Inline XBRL (E113): 410, no data",
    "GET /v1/entity/sfdr-statement.xbrl": "retired entity SFDR PAI XBRL (E113): 410, no data",
    # blank upload templates — no data
    "GET /v1/arrears/template.csv": "blank template", "GET /v1/assetmgmt/holdings/template.xlsx": "blank template",
    "GET /v1/bank/assets/attributes/template.xlsx": "blank template", "GET /v1/bank/assets/template.xlsx": "blank template",
    "GET /v1/entity-structure/template.csv": "blank template", "GET /v1/gl/template.csv": "blank template",
    "GET /v1/holdings/template.csv": "blank template", "GET /v1/insurance/policies/template.xlsx": "blank template",
    "GET /v1/prices/template.csv": "blank template", "GET /v1/realestate/properties/template.xlsx": "blank template",
    "GET /v1/supply/plots/template.xlsx": "blank template", "GET /v1/eudr/intake/{book}/template.xlsx": "blank template",
    "GET /v1/supply/sites/template.xlsx": "blank template", "GET /v1/supply/sites/year-end/template.xlsx": "blank template",
}

# routes that resolve the caller's organisation anonymously AND take an id of a shared reference record (not a tenant
# record), whose results are then scoped to the caller's organisation
REFERENCE_ID_ROUTES: dict[str, str] = {
    "GET /v1/supply/commodity/{commodity_id}": "commodity is shared reference data; plots and exposure are filtered to the caller's org",
    "GET /v1/supply/commodity/{commodity_id}/world-crop": "commodity is shared reference data; the figures are FAOSTAT "
                                                         "world and origin production only — no organisation's data",
    "GET /v1/supply/commodity/{commodity_id}/outlook": "commodity is shared reference data; the outlook reads published "
                                                      "calibrations, and 'own origins' are the caller's org plots only",
    "GET /v1/issuers/{issuer_id}": "issuer is shared reference data; served only when one of the caller's funds holds it (404 otherwise)",
}
