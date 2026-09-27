"""Share classes — the versions of a fund sold to investors: same portfolio, own ISIN, currency, hedging, and whether
income is paid out or reinvested. The European ESG Template is one row per active share class; an ISIN a client holds
that is one of the organisation's own classes resolves to its fund (so it can be looked through).

Changes are the manager's facts about its own products (principle 1): written directly, validated, audited. A class
is closed, never deleted, so a published EET that listed it still reads.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

DISTRIBUTION = ("accumulating", "distributing")


class ShareClassError(ValueError):
    pass


def isin_valid(isin: str) -> bool:
    """ISO 6166: 2-letter country, 9 alphanumerics, 1 check digit (Luhn over the letters-as-numbers expansion)."""
    s = (isin or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", s):
        return False
    digits = "".join(str(int(c, 36)) for c in s[:-1])
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            d = d - 9 if d > 9 else d
        total += d
    return (10 - total % 10) % 10 == int(s[-1])


def _clean(session: Session, body: dict, partial: bool = False) -> dict:
    from services.reference.fx import supported_currencies
    out: dict = {}
    if "isin" in body or not partial:
        isin = (body.get("isin") or "").strip().upper()
        if not isin_valid(isin):
            raise ShareClassError(f"'{isin}' is not a valid ISIN (2-letter country, 9 characters, check digit)")
        out["isin"] = isin
    if "name" in body or not partial:
        name = (body.get("name") or "").strip()
        if not name or len(name) > 255:
            raise ShareClassError("a share class needs a name (at most 255 characters)")
        out["name"] = name
    if "currency" in body or not partial:
        ccy = (body.get("currency") or "").strip().upper()
        if ccy not in set(supported_currencies(session)):
            raise ShareClassError(f"'{ccy}' is not a currency we can convert (ISO 4217, e.g. EUR, USD)")
        out["currency"] = ccy
    if "hedged" in body or not partial:
        out["hedged"] = bool(body.get("hedged"))
    if "distribution" in body or not partial:
        dist = (body.get("distribution") or "").strip().lower()
        if dist not in DISTRIBUTION:
            raise ShareClassError("distribution is 'accumulating' (income reinvested) or 'distributing' (paid out)")
        out["distribution"] = dist
    if body.get("launch_date"):
        try:
            d = date.fromisoformat(str(body["launch_date"])[:10])
        except ValueError:
            raise ShareClassError("launch_date must be YYYY-MM-DD")
        if d > date.today():
            raise ShareClassError("launch_date can't be in the future")
        out["launch_date"] = d
    return out


def _fund_of_org(session: Session, org_id: str, fund_id: str) -> None:
    if not session.execute(text("SELECT 1 FROM funds WHERE fund_id = CAST(:f AS uuid) AND org_id = CAST(:o AS uuid)"),
                           {"f": fund_id, "o": org_id}).first():
        raise ShareClassError("fund not found")


def list_classes(session: Session, org_id: str, fund_id: Optional[str] = None) -> list[dict]:
    rows = session.execute(text("""
        SELECT c.share_class_id::text AS share_class_id, c.fund_id::text AS fund_id, f.name AS fund_name, c.isin, c.name,
               c.currency, c.hedged, c.distribution, c.launch_date, c.status, c.updated_at
        FROM fund_share_classes c JOIN funds f ON f.fund_id = c.fund_id
        WHERE c.org_id = CAST(:o AS uuid) AND (CAST(:f AS uuid) IS NULL OR c.fund_id = CAST(:f AS uuid))
        ORDER BY f.name, c.status, c.name
    """), {"o": org_id, "f": fund_id}).mappings().all()
    return [{**dict(r), "launch_date": r["launch_date"].isoformat() if r["launch_date"] else None,
             "updated_at": r["updated_at"].isoformat()} for r in rows]


def create(session: Session, org_id: str, fund_id: str, body: dict, user_id: Optional[str]) -> dict:
    _fund_of_org(session, org_id, fund_id)
    v = _clean(session, body)
    try:
        with session.begin_nested():
            sid = session.execute(text("""
                INSERT INTO fund_share_classes (org_id, fund_id, isin, name, currency, hedged, distribution, launch_date,
                                                created_by, updated_by)
                VALUES (CAST(:o AS uuid), CAST(:f AS uuid), :isin, :name, :currency, :hedged, :distribution, :launch_date,
                        CAST(:u AS uuid), CAST(:u AS uuid))
                RETURNING share_class_id::text
            """), {"o": org_id, "f": fund_id, "u": user_id, "launch_date": None, **v}).scalar()
    except IntegrityError:
        raise ShareClassError(f"ISIN {v['isin']} is already registered as one of your share classes")
    return next(c for c in list_classes(session, org_id, fund_id) if c["share_class_id"] == sid)


def update(session: Session, org_id: str, share_class_id: str, body: dict, user_id: Optional[str]) -> dict:
    v = _clean(session, body, partial=True)
    if "status" in body:
        if body["status"] not in ("active", "closed"):
            raise ShareClassError("status is 'active' or 'closed'")
        v["status"] = body["status"]
    if not v:
        raise ShareClassError("nothing to change")
    sets = ", ".join(f"{k} = :{k}" for k in v)
    try:
        with session.begin_nested():
            n = session.execute(text(f"""
                UPDATE fund_share_classes SET {sets}, updated_by = CAST(:u AS uuid), updated_at = now()
                WHERE share_class_id = CAST(:s AS uuid) AND org_id = CAST(:o AS uuid)
            """), {**v, "u": user_id, "s": share_class_id, "o": org_id}).rowcount
    except IntegrityError:
        raise ShareClassError(f"ISIN {v.get('isin')} is already registered as one of your share classes")
    if not n:
        raise ShareClassError("share class not found")
    return next(c for c in list_classes(session, org_id) if c["share_class_id"] == share_class_id)


def resolve_isin(session: Session, org_id: str, isin: str) -> Optional[dict]:
    """An ISIN that is one of the organisation's own share classes → its class and fund (None otherwise)."""
    r = session.execute(text("""
        SELECT c.share_class_id::text AS share_class_id, c.fund_id::text AS fund_id, f.name AS fund_name, c.name, c.status
        FROM fund_share_classes c JOIN funds f ON f.fund_id = c.fund_id
        WHERE c.org_id = CAST(:o AS uuid) AND c.isin = :i
    """), {"o": org_id, "i": (isin or "").strip().upper()}).mappings().first()
    return dict(r) if r else None
