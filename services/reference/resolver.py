"""ReferenceResolver — ISIN → issuer + security, from open data, auditable.

This is the spine of "onboard with ISINs alone". Given an ISIN a client holds:

  1. Cache hit — already in our `securities` golden source → return it.
  2. Miss     — resolve via GLEIF (ISIN→LEI→identity), upsert the issuer (keyed
                by LEI) and the security, each stamped with source + vintage.
  3. Always   — write a `reference_resolution_log` row: the audit trail a filing
                cites ("N resolved against GLEIF vintage YYYY-MM-DD, M unmatched").

Honesty rules baked in:
  * An unmatched ISIN is a first-class, reported outcome — never a fabricated
    issuer. It is logged 'unmatched' and excluded from the book.
  * A GLEIF outage is 'error', kept distinct from 'unmatched', so coverage is
    never understated because the source was momentarily down.
  * On re-resolution we do NOT clobber client-enriched fields (sector/NACE the
    client supplied); GLEIF only fills what we don't already have.
  * Sector/NACE is left NULL when GLEIF can't supply it — surfaced downstream as
    a coverage gap for the client, not guessed.

The resolver takes a caller-managed SQLAlchemy session so a whole onboarding
batch commits (or rolls back) as one transaction.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.reference import gleif
from services.reference.gleif import GleifError

logger = logging.getLogger(__name__)

# Valid securities.asset_class values a client may hint (schema CHECK).
_ASSET_CLASSES = {"equity", "corporate_bond", "sovereign_bond", "securitized", "etf", "fund", "other"}


@dataclass
class Resolution:
    isin: str
    status: str                       # resolved | cached | unmatched | error
    issuer_id: Optional[str] = None
    security_id: Optional[str] = None
    lei: Optional[str] = None
    issuer_name: Optional[str] = None
    country: Optional[str] = None
    sector_known: bool = False        # False = NACE/sector gap the client must fill
    source: Optional[str] = None
    data_vintage: Optional[date] = None
    detail: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["data_vintage"] = self.data_vintage.isoformat() if self.data_vintage else None
        return d


def _find_cached_security(session: Session, isin: str) -> Optional[dict]:
    row = session.execute(
        text(
            """
            SELECT s.security_id, s.issuer_id, i.lei, i.name AS issuer_name,
                   i.country, i.nace_code, i.source AS issuer_source, i.data_vintage
            FROM   securities s
            JOIN   issuers i ON i.issuer_id = s.issuer_id
            WHERE  s.isin = :isin
            """
        ),
        {"isin": isin},
    ).mappings().first()
    return dict(row) if row else None


def _upsert_issuer(session: Session, rec: gleif.GleifRecord) -> str:
    """Insert the issuer if new (keyed by LEI); enrich-without-clobber if known.

    On conflict we only refresh identity we can safely own (name, resolved_at)
    and back-fill country if we had none — we never overwrite a client-supplied
    sector/NACE. Returns the issuer_id either way.
    """
    row = session.execute(
        text(
            """
            INSERT INTO issuers (lei, name, issuer_type, country, source, data_vintage, resolved_at)
            VALUES (:lei, :name, :itype, :country, 'gleif', :vintage, now())
            ON CONFLICT (lei) DO UPDATE
                SET name        = EXCLUDED.name,
                    country     = COALESCE(issuers.country, EXCLUDED.country),
                    resolved_at = now(),
                    updated_at  = now()
            RETURNING issuer_id, nace_code
            """
        ),
        {
            "lei": rec.lei,
            "name": rec.name,
            "itype": rec.issuer_type,
            "country": rec.country,
            "vintage": rec.data_vintage,
        },
    ).mappings().one()
    return str(row["issuer_id"])


def _upsert_security(session: Session, isin: str, issuer_id: str, name: str,
                     asset_class: str, currency: Optional[str], vintage: date) -> str:
    row = session.execute(
        text(
            """
            INSERT INTO securities (isin, name, issuer_id, asset_class, currency, source, data_vintage)
            VALUES (:isin, :name, :issuer_id, :aclass, :ccy, 'gleif', :vintage)
            ON CONFLICT (isin) DO UPDATE
                SET issuer_id    = EXCLUDED.issuer_id,
                    asset_class  = EXCLUDED.asset_class,
                    data_vintage = EXCLUDED.data_vintage
            RETURNING security_id
            """
        ),
        {"isin": isin, "name": name, "issuer_id": issuer_id,
         "aclass": asset_class, "ccy": currency, "vintage": vintage},
    ).mappings().one()
    return str(row["security_id"])


def _log(session: Session, res: Resolution, org_id: Optional[str]) -> None:
    session.execute(
        text(
            """
            INSERT INTO reference_resolution_log
                (isin, status, issuer_id, security_id, lei, source, data_vintage, detail, org_id)
            VALUES (:isin, :status, :issuer_id, :security_id, :lei, :source, :vintage, :detail, :org_id)
            """
        ),
        {
            "isin": res.isin, "status": res.status, "issuer_id": res.issuer_id,
            "security_id": res.security_id, "lei": res.lei,
            "source": res.source or "gleif", "vintage": res.data_vintage,
            "detail": res.detail, "org_id": org_id,
        },
    )


def resolve_isin(
    session: Session,
    isin: str,
    *,
    org_id: Optional[str] = None,
    asset_class: str = "equity",
    currency: Optional[str] = None,
    log: bool = True,
) -> Resolution:
    """Resolve one ISIN to an issuer+security, writing provenance + an audit row."""
    isin = (isin or "").strip().upper()
    asset_class = asset_class if asset_class in _ASSET_CLASSES else "equity"

    if len(isin) != 12 or not isin.isalnum():
        res = Resolution(isin=isin, status="unmatched", detail="malformed ISIN (not 12 alphanumerics)")
        if log:
            _log(session, res, org_id)
        return res

    # 1. Cache — already in our golden source.
    cached = _find_cached_security(session, isin)
    if cached:
        res = Resolution(
            isin=isin, status="cached",
            issuer_id=str(cached["issuer_id"]), security_id=str(cached["security_id"]),
            lei=cached["lei"], issuer_name=cached["issuer_name"], country=cached["country"],
            sector_known=cached["nace_code"] is not None,
            source=cached["issuer_source"], data_vintage=cached["data_vintage"],
        )
        if log:
            _log(session, res, org_id)
        return res

    # 2. Miss — resolve against GLEIF.
    try:
        rec = gleif.resolve_isin(isin)
    except GleifError as exc:
        res = Resolution(isin=isin, status="error", source="gleif", detail=str(exc)[:400])
        if log:
            _log(session, res, org_id)
        logger.warning("GLEIF error resolving %s: %s", isin, exc)
        return res

    if rec is None:
        res = Resolution(isin=isin, status="unmatched", source="gleif",
                         detail="no LEI mapped to this ISIN in GLEIF")
        if log:
            _log(session, res, org_id)
        return res

    # 3. Persist issuer + security with provenance.
    issuer_id = _upsert_issuer(session, rec)
    security_id = _upsert_security(session, isin, issuer_id, rec.name, asset_class, currency, rec.data_vintage)
    res = Resolution(
        isin=isin, status="resolved", issuer_id=issuer_id, security_id=security_id,
        lei=rec.lei, issuer_name=rec.name, country=rec.country,
        sector_known=False,  # GLEIF never supplies NACE — a real, disclosed gap
        source="gleif", data_vintage=rec.data_vintage,
    )
    if log:
        _log(session, res, org_id)
    return res


def link_isin_to_record(
    session: Session,
    isin: str,
    rec: gleif.GleifRecord,
    *,
    org_id: Optional[str] = None,
    asset_class: str = "equity",
    log: bool = True,
) -> Resolution:
    """Persist an ISIN → issuer + security link from an ALREADY-fetched GLEIF
    record (e.g. one found by name when GLEIF's ISIN mapping had a gap).

    This fills a hole in GLEIF's ISIN→LEI coverage with our own: the security row
    now maps the ISIN to the issuer, so a later customer upload of that ISIN is a
    normal cache hit — no name matching on the customer path.
    """
    isin = (isin or "").strip().upper()
    issuer_id = _upsert_issuer(session, rec)
    security_id = _upsert_security(session, isin, issuer_id, rec.name, asset_class, None, rec.data_vintage)
    res = Resolution(
        isin=isin, status="resolved", issuer_id=issuer_id, security_id=security_id,
        lei=rec.lei, issuer_name=rec.name, country=rec.country, sector_known=False,
        source="gleif", data_vintage=rec.data_vintage,
        detail="ISIN linked via GLEIF name lookup (ISIN→LEI mapping gap)",
    )
    if log:
        _log(session, res, org_id)
    return res


def resolve_batch(
    session: Session,
    isins: list[str],
    *,
    org_id: Optional[str] = None,
) -> dict:
    """Resolve many ISINs and return per-ISIN results plus a coverage summary.

    De-duplicates the input (a book often repeats an issuer across positions) so
    GLEIF is hit once per distinct ISIN. The summary is the raw material for the
    'onboarding coverage' the client sees — honest counts, no hidden drops.
    """
    seen: dict[str, Resolution] = {}
    for raw in isins:
        isin = (raw or "").strip().upper()
        if isin in seen:
            continue
        seen[isin] = resolve_isin(session, isin, org_id=org_id)

    resolutions = list(seen.values())
    by_status: dict[str, int] = {}
    for r in resolutions:
        by_status[r.status] = by_status.get(r.status, 0) + 1

    matched = by_status.get("resolved", 0) + by_status.get("cached", 0)
    total = len(resolutions)
    sector_gaps = [r.isin for r in resolutions if r.status in ("resolved", "cached") and not r.sector_known]

    return {
        "resolutions": [r.to_dict() for r in resolutions],
        "summary": {
            "distinct_isins": total,
            "matched": matched,
            "match_rate_pct": round(100.0 * matched / total, 1) if total else 0.0,
            "by_status": by_status,
            "unmatched_isins": [r.isin for r in resolutions if r.status == "unmatched"],
            "errored_isins": [r.isin for r in resolutions if r.status == "error"],
            "sector_gap_isins": sector_gaps,  # matched but NACE unknown → client input needed
        },
    }
