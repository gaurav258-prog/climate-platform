"""An organisation's own (treasury) exchange rates — governed (multi-currency decision 4, 2026-09-26).

Principle 1 (the client wins on facts about their own book): when an organisation has supplied a rate for the day
(closing) or for the exact period (average), its rate converts its amounts. It is ALWAYS compared with the official
rate for the same day / period (ECB, legal peg, IMF); a difference beyond the organisation's tolerance
(fx_client_rate_tolerance_pct) is a failed check — a second person must accept it (intake) or the input is refused
(direct forms, which have no approval step). Submissions are append-only; the latest for a key wins.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

CLOSING_MAX_AGE_DAYS = 7


def _latest(session: Session, org_id: str, ccy: str, basis: str, on: date, start: Optional[date]) -> Optional[dict]:
    if basis == "closing":
        return session.execute(text("""
            SELECT units_per_eur, rate_date, source_note, submitted_at FROM fx_client_rates
            WHERE org_id = CAST(:o AS uuid) AND ccy = :c AND basis = 'closing' AND rate_date <= :d
            ORDER BY rate_date DESC, submitted_at DESC LIMIT 1
        """), {"o": org_id, "c": ccy, "d": on}).mappings().first()
    return session.execute(text("""
        SELECT units_per_eur, rate_date, period_start, source_note, submitted_at FROM fx_client_rates
        WHERE org_id = CAST(:o AS uuid) AND ccy = :c AND basis = 'period_average' AND rate_date = :d AND period_start = :s
        ORDER BY submitted_at DESC LIMIT 1
    """), {"o": org_id, "c": ccy, "d": on, "s": start}).mappings().first()


def resolve(session: Session, org_id: Optional[str], ccy: str, on: date, *, average: bool = False,
            start: Optional[date] = None, official: Optional[dict] = None, tolerance_pct: float = 1.0) -> Optional[dict]:
    """The organisation's own rate for this conversion, compared with `official` (the rate the official sources
    give for the same day / period). None when the organisation has no usable rate — the official one applies."""
    if not org_id or ccy == "EUR":
        return None
    row = _latest(session, org_id, ccy, "period_average" if average else "closing", on, start)
    if not row:
        return None
    age = (on - row["rate_date"]).days
    if not average and age > CLOSING_MAX_AGE_DAYS:
        return None                                   # too old to stand for the day: the official rate applies
    u = float(row["units_per_eur"])
    out = {"currency": ccy, "rate": 1.0 / u, "units_per_eur": u, "rate_date": row["rate_date"].isoformat(),
           "source": "client", "basis": "period_average" if average else "closing", "age_days": age, "stale": False,
           "official": None, "difference_pct": None, "outside_tolerance": False}
    if average:
        out.update({"period_start": start.isoformat(), "period_end": on.isoformat()})
    if official and official.get("units_per_eur"):
        ou = float(official["units_per_eur"])
        diff = abs(u - ou) / ou * 100.0
        out.update({"official": {k: official.get(k) for k in ("units_per_eur", "source", "basis", "rate_date")},
                    "difference_pct": round(diff, 3), "outside_tolerance": diff > tolerance_pct})
        out["note"] = (f"your rate {u:g} per EUR; {official.get('source', 'official').upper()} {ou:g} — {diff:.2f}% apart"
                       + (f", beyond your {tolerance_pct:g}% tolerance" if diff > tolerance_pct else ""))
    else:
        out["note"] = f"your rate {u:g} per EUR (no official rate to compare)"
    return out


def submit(session: Session, org_id: str, rows: list[dict], user_id: Optional[str]) -> dict:
    """Store the organisation's rates. rows: {currency, rate_date, units_per_eur, basis?='closing', period_start?,
    note?}. Each row is checked (a currency we know, a positive rate, a past date, a period for an average); rows that
    fail are reported with the reason. Returns the accepted rows compared with the official rate."""
    from services.intake.money import MoneyError, parse_book_date, validate_declaration
    from services.reference.fx import FxError, average_rate, rate_for
    accepted, refused = [], []
    for i, r in enumerate(rows, start=1):
        try:
            ccy, _ = validate_declaration(session, r.get("currency"), None)
            if not ccy or ccy == "EUR":
                raise MoneyError("currency must be a non-euro ISO 4217 code")
            d = parse_book_date(r.get("rate_date"))
            if d is None or d > date.today():
                raise MoneyError("rate_date must be a past date (YYYY-MM-DD)")
            u = float(str(r.get("units_per_eur")).replace(",", ""))
            if not u > 0:
                raise MoneyError("units_per_eur must be positive (units of the currency per 1 EUR, as the ECB quotes)")
            basis = (r.get("basis") or "closing").strip().lower()
            if basis not in ("closing", "period_average"):
                raise MoneyError("basis must be 'closing' or 'period_average'")
            start = parse_book_date(r.get("period_start")) if basis == "period_average" else None
            if basis == "period_average" and (start is None or start >= d):
                raise MoneyError("an average needs period_start before rate_date")
        except (MoneyError, ValueError, TypeError) as e:
            refused.append({"row": i, "reason": str(e)})
            continue
        session.execute(text("""
            INSERT INTO fx_client_rates (org_id, ccy, basis, period_start, rate_date, units_per_eur, source_note, submitted_by)
            VALUES (CAST(:o AS uuid), :c, :b, :s, :d, :u, :n, CAST(:by AS uuid))
        """), {"o": org_id, "c": ccy, "b": basis, "s": start, "d": d, "u": u, "n": (r.get("note") or "")[:200] or None,
               "by": user_id})
        try:
            off = average_rate(session, ccy, start, d) if basis == "period_average" else rate_for(session, ccy, d)
        except FxError:
            off = None
        diff = round(abs(u - off["units_per_eur"]) / off["units_per_eur"] * 100, 3) if off and off.get("units_per_eur") else None
        accepted.append({"currency": ccy, "basis": basis, "rate_date": d.isoformat(), "units_per_eur": u,
                         "official_units_per_eur": off.get("units_per_eur") if off else None,
                         "official_source": off.get("source") if off else None, "difference_pct": diff})
    return {"n_accepted": len(accepted), "accepted": accepted[:200], "n_refused": len(refused), "refused": refused[:50]}


def latest_rates(session: Session, org_id: str, limit: int = 200) -> list[dict]:
    rows = session.execute(text("""
        SELECT DISTINCT ON (ccy, basis, period_start, rate_date) ccy, basis, period_start, rate_date,
               CAST(units_per_eur AS FLOAT) AS units_per_eur, source_note, submitted_at
        FROM fx_client_rates WHERE org_id = CAST(:o AS uuid)
        ORDER BY ccy, basis, period_start, rate_date DESC, submitted_at DESC LIMIT :l
    """), {"o": org_id, "l": limit}).mappings().all()
    return [{**dict(r), "rate_date": r["rate_date"].isoformat(),
             "period_start": r["period_start"].isoformat() if r["period_start"] else None,
             "submitted_at": str(r["submitted_at"])[:19]} for r in rows]
