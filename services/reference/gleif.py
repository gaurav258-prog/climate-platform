"""GLEIF adapter — issuer identity from the open LEI system.

GLEIF (the Global Legal Entity Identifier Foundation) publishes the LEI system
as fully open data: a free, keyless REST API and daily bulk files. It is the
authoritative, regulator-recognised source for "who is the legal entity behind
this security", and it exposes the ISIN→LEI mapping we need to turn a client's
bare ISIN list into issuers.

What GLEIF gives us, honestly:
  * identity      — LEI, legal name, country, jurisdiction, legal form, status
  * an address    — legal + headquarters city/country/region (a footprint seed,
                    geocoded to lat/lon downstream; GLEIF gives no coordinates)

What it does NOT give us (so we never pretend it does):
  * NACE / industry / sector  — absent from LEI records. Sector is left NULL and
    surfaced as a coverage gap for the client to supply, not guessed.

No API key. Base rate limits are generous but real, so we back off on 429.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import requests

logger = logging.getLogger(__name__)

GLEIF_BASE = "https://api.gleif.org/api/v1"
_HEADERS = {"Accept": "application/vnd.api+json"}
_TIMEOUT = 20
_MAX_RETRIES = 3
ADAPTER_SOURCE = "gleif"


class GleifError(RuntimeError):
    """The source was unreachable or misbehaved — distinct from 'no match'.

    A network/5xx failure must NOT be silently treated as 'ISIN unmatched':
    unmatched is a real, reportable outcome; an outage is a retry-or-surface
    condition. Callers distinguish the two so a filing never under-reports
    coverage because GLEIF happened to be down.
    """


@dataclass
class GleifRecord:
    """Normalized subset of a GLEIF LEI record. Provenance travels with it."""

    lei: str
    name: str
    country: Optional[str] = None            # legal address country (ISO-2)
    jurisdiction: Optional[str] = None       # e.g. US-CA, FR
    legal_form: Optional[str] = None         # ELF code, e.g. H1UM
    entity_category: Optional[str] = None    # GENERAL / FUND / BRANCH / SOLE_PROPRIETOR ...
    entity_status: Optional[str] = None      # ACTIVE / INACTIVE
    hq_city: Optional[str] = None
    hq_country: Optional[str] = None
    hq_region: Optional[str] = None
    hq_address_lines: list[str] = field(default_factory=list)
    source: str = ADAPTER_SOURCE
    data_vintage: date = field(default_factory=date.today)

    @property
    def issuer_type(self) -> str:
        """Map GLEIF entity category to our issuers.issuer_type vocabulary.

        Conservative: only 'fund' is inferable from GLEIF's category. Everything
        else defaults to 'corporate' — sovereign/supranational/municipal are not
        reliably flagged by GLEIF category and are set from the client's own
        instrument metadata (e.g. a sovereign bond) upstream, not guessed here.
        """
        if (self.entity_category or "").upper() == "FUND":
            return "fund"
        return "corporate"


def _request(path: str, params: Optional[dict] = None) -> dict:
    """GET against the GLEIF API with bounded retries on transient failures."""
    url = f"{GLEIF_BASE}/{path}"
    last_exc: Optional[Exception] = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
        except requests.RequestException as exc:  # DNS, connection, timeout
            last_exc = exc
            logger.warning("GLEIF request error (attempt %d/%d): %s", attempt, _MAX_RETRIES, exc)
            time.sleep(min(2 ** attempt, 8))
            continue

        if resp.status_code == 429:  # rate limited — respect and retry
            wait = int(resp.headers.get("Retry-After", 2 ** attempt))
            logger.info("GLEIF rate limited; sleeping %ds", wait)
            time.sleep(min(wait, 10))
            continue
        if resp.status_code >= 500:
            last_exc = GleifError(f"GLEIF {resp.status_code} for {url}")
            time.sleep(min(2 ** attempt, 8))
            continue
        if resp.status_code == 404:
            return {}
        if resp.status_code != 200:
            raise GleifError(f"GLEIF {resp.status_code} for {url}: {resp.text[:200]}")
        try:
            return resp.json()
        except ValueError as exc:
            raise GleifError(f"GLEIF returned non-JSON for {url}") from exc

    raise GleifError(f"GLEIF unreachable after {_MAX_RETRIES} attempts: {url}") from last_exc


def _parse_record(rec: dict) -> Optional[GleifRecord]:
    attrs = rec.get("attributes") or {}
    lei = attrs.get("lei")
    entity = attrs.get("entity") or {}
    name = (entity.get("legalName") or {}).get("name")
    if not lei or not name:
        return None
    legal_addr = entity.get("legalAddress") or {}
    hq = entity.get("headquartersAddress") or {}
    return GleifRecord(
        lei=lei,
        name=name,
        country=legal_addr.get("country"),
        jurisdiction=entity.get("jurisdiction"),
        legal_form=(entity.get("legalForm") or {}).get("id"),
        entity_category=entity.get("category"),
        entity_status=entity.get("status"),
        hq_city=hq.get("city"),
        hq_country=hq.get("country"),
        hq_region=hq.get("region"),
        hq_address_lines=list(hq.get("addressLines") or []),
    )


def resolve_isin(isin: str) -> Optional[GleifRecord]:
    """Resolve an ISIN to its issuer via GLEIF's ISIN→LEI mapping.

    Returns None for a genuine no-match (the ISIN exists but GLEIF has no LEI
    mapping, or it is malformed). Raises GleifError only for source failures —
    callers must not conflate 'unmatched' with 'GLEIF was down'.
    """
    isin = (isin or "").strip().upper()
    if len(isin) != 12 or not isin.isalnum():
        return None  # not a well-formed ISIN — a client-data problem, not a source outage
    payload = _request("lei-records", params={"filter[isin]": isin, "page[size]": 1})
    data = payload.get("data") or []
    if not data:
        return None
    rec = _parse_record(data[0])
    if rec and len(data) > 1:
        logger.info("ISIN %s mapped to %d LEIs; took first (%s)", isin, len(data), rec.lei)
    return rec


def resolve_name(name: str) -> Optional[GleifRecord]:
    """Resolve a company by legal name via GLEIF — a fallback for when GLEIF's
    ISIN→LEI mapping file has a gap but the entity clearly exists.

    ONLY safe with a curated, known name (as in our universe loader), never with
    free-form customer input: name matching is inherently ambiguous, so this must
    not sit on the ISIN-only customer path. Returns the top legal-name match.
    """
    name = (name or "").strip()
    if len(name) < 3:
        return None
    payload = _request("lei-records", params={"filter[entity.legalName]": name, "page[size]": 1})
    data = payload.get("data") or []
    if not data:
        return None
    return _parse_record(data[0])


def fetch_lei(lei: str) -> Optional[GleifRecord]:
    """Fetch a GLEIF record directly by LEI (enrichment / re-verification)."""
    lei = (lei or "").strip().upper()
    if len(lei) != 20 or not lei.isalnum():
        return None
    payload = _request(f"lei-records/{lei}")
    data = payload.get("data")
    if not data:
        return None
    return _parse_record(data)
