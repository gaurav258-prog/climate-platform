"""FX normalization — convert a holding's native-currency value into EUR so
every downstream PAI figure (financed emissions, WACI, weights) is
currency-correct across a mixed-currency book.

Design, in plain English:
  * A fund can hold USD, GBP, JPY … lines. SFDR figures roll up in EUR, so each
    position's value must be converted BEFORE it is weighted or attributed.
  * Rates live in the `fx_rates` table as EUR-per-one-unit-of-currency, dated.
    We pick the most recent rate on-or-before the position's as-of date — the
    rate that was true when the book was struck, not today's rate.
  * Source of truth is the ECB reference rate (free, no licence); the loader
    script `scripts/load_fx_rates.py` pulls it. The table is seeded at migration
    time with a labelled fallback set so tests and offline runs are deterministic
    and EUR is never silently assumed for a non-EUR line.
  * EUR is always 1.0. An unknown currency is a hard, surfaced error — we never
    guess a rate.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import text

# Labelled fallback: EUR per 1 unit of currency, ECB reference rates 2023-12-29.
# Used only when the fx_rates table has no row for the currency (offline/tests).
# The loader overwrites these with live ECB history keyed by date.
_FALLBACK_DATE = date(2023, 12, 29)
FALLBACK_EUR_PER_UNIT: dict[str, float] = {
    "EUR": 1.0,
    "USD": 0.90580, "GBP": 1.15130, "CHF": 1.08000, "JPY": 0.0063967,
    "SEK": 0.090123, "NOK": 0.088964, "DKK": 0.134176, "CAD": 0.683000,
    "AUD": 0.614900, "CNY": 0.127374, "HKD": 0.115856, "SGD": 0.685350,
    "PLN": 0.230442, "CZK": 0.040477, "HUF": 0.0026080, "NZD": 0.573100,
}


class FxError(ValueError):
    """Raised when a currency cannot be converted — no rate anywhere."""


def _norm_ccy(currency: Optional[str]) -> str:
    # A blank/None currency is NOT EUR — it is unknown. Surfacing it honours this module's
    # contract ("EUR is never silently assumed for a non-EUR line"); the caller must pass an
    # explicit "EUR" for a EUR line (audit T9).
    ccy = (currency or "").strip().upper()
    if not ccy:
        raise FxError("No currency supplied — cannot convert to EUR (EUR is never assumed "
                      "for a blank currency; pass an explicit 'EUR' for a euro line)")
    return ccy


def to_eur(session, amount: float, currency: Optional[str],
           on_date: Optional[date] = None) -> dict:
    """Convert `amount` in `currency` to EUR as of `on_date`.

    Returns {eur, rate, rate_date, currency, source}. Raises FxError if the
    currency is unknown (never assumes 1.0 for a non-EUR line)."""
    ccy = _norm_ccy(currency)
    on_date = on_date or date.today()
    if ccy == "EUR":
        return {"eur": round(float(amount), 2), "rate": 1.0, "rate_date": None,
                "currency": "EUR", "source": "identity"}

    row = session.execute(text("""
        SELECT eur_per_unit, rate_date FROM fx_rates
         WHERE ccy = :c AND rate_date <= :d
         ORDER BY rate_date DESC LIMIT 1
    """), {"c": ccy, "d": on_date}).mappings().first()
    if row is None:
        # No rate on-or-before the date; fall back to the earliest available.
        row = session.execute(text("""
            SELECT eur_per_unit, rate_date FROM fx_rates
             WHERE ccy = :c ORDER BY rate_date ASC LIMIT 1
        """), {"c": ccy}).mappings().first()

    if row is not None:
        rate = float(row["eur_per_unit"])
        return {"eur": round(float(amount) * rate, 2), "rate": rate,
                "rate_date": row["rate_date"].isoformat() if row["rate_date"] else None,
                "currency": ccy, "source": "ecb"}

    if ccy in FALLBACK_EUR_PER_UNIT:
        rate = FALLBACK_EUR_PER_UNIT[ccy]
        return {"eur": round(float(amount) * rate, 2), "rate": rate,
                "rate_date": _FALLBACK_DATE.isoformat(), "currency": ccy, "source": "fallback"}

    raise FxError(f"No FX rate for currency {ccy!r} — cannot convert to EUR")


def supported_currencies(session) -> list[str]:
    """Currencies we can convert (table ∪ fallback), for UI validation."""
    rows = session.execute(text("SELECT DISTINCT ccy FROM fx_rates")).scalars().all()
    return sorted(set(rows) | set(FALLBACK_EUR_PER_UNIT))
