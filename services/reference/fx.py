"""FX normalization — convert a holding's native-currency value into EUR so
every downstream PAI figure (financed emissions, WACI, weights) is
currency-correct across a mixed-currency book.

Design, in plain English:
  * A fund can hold USD, GBP, JPY … lines. SFDR figures roll up in EUR, so each
    position's value must be converted BEFORE it is weighted or attributed.
  * Rates live in the `fx_rates` table as EUR-per-one-unit-of-currency, dated.
    We pick the most recent rate on-or-before the position's as-of date — the
    rate that was true when the book was struck, not today's rate.
  * Rates come from several official sources, chosen in a fixed order by the source registry
    (services/reference/fx_sources.py): ECB daily reference rates, rates fixed by law (fx_pegs), IMF
    month-end rates. Each conversion states its source, date, kind of figure, age, and whether it is stale. The table is seeded at migration
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


def rate_for(session, currency: Optional[str], on_date: Optional[date] = None) -> dict:
    """The EUR rate for one currency on one book date, chosen by the source registry (fx_sources.SOURCES, in order).

    Returns {currency, rate (EUR per unit), units_per_eur, rate_date, source, basis, age_days, stale, note}.
    First source with a rate on-or-before the date within its own max age wins; otherwise the freshest rate found is
    returned with stale=True (a person must accept it). Never assumes a rate: unknown currency → FxError."""
    from services.reference.fx_sources import SOURCES
    ccy = _norm_ccy(currency)
    on_date = on_date or date.today()
    if ccy == "EUR":
        return {"currency": "EUR", "rate": 1.0, "units_per_eur": 1.0, "rate_date": None, "source": "identity",
                "basis": "identity", "age_days": 0, "stale": False, "note": None}
    found: list[dict] = []
    for src in SOURCES:
        if src.key == "peg":
            p = session.execute(text("""
                SELECT units_per_eur, valid_from, legal_basis FROM fx_pegs
                WHERE ccy = :c AND valid_from <= :d AND (valid_to IS NULL OR valid_to >= :d)
                ORDER BY valid_from DESC LIMIT 1
            """), {"c": ccy, "d": on_date}).mappings().first()
            if p:
                u = float(p["units_per_eur"])
                return {"currency": ccy, "rate": round(1.0 / u, 12), "units_per_eur": u, "rate_date": None,
                        "source": "peg", "basis": "fixed_peg", "age_days": 0, "stale": False,
                        "note": f"fixed since {p['valid_from'].isoformat()} — {p['legal_basis']}"}
            continue
        r = session.execute(text("""
            SELECT eur_per_unit, units_per_eur, rate_date FROM fx_rates
            WHERE ccy = :c AND source = :s AND basis = :b AND rate_date <= :d ORDER BY rate_date DESC LIMIT 1
        """), {"c": ccy, "s": src.key, "b": src.basis, "d": on_date}).mappings().first()
        if not r:
            continue
        age = (on_date - r["rate_date"]).days
        row = {"currency": ccy, "rate": float(r["eur_per_unit"]),
               "units_per_eur": float(r["units_per_eur"]) if r["units_per_eur"] is not None else None,
               "rate_date": r["rate_date"].isoformat(), "source": src.key, "basis": src.basis, "age_days": age,
               "stale": False, "note": None}
        if src.max_age_days is None or age <= src.max_age_days:
            return row
        found.append({**row, "stale": True,
                      "note": f"latest {src.key.upper()} rate is {age} days before the book date (limit {src.max_age_days})"})
    if found:
        return min(found, key=lambda x: x["age_days"])
    # nothing on or before the book date: the earliest later rate, clearly marked — never silently
    r = session.execute(text("""
        SELECT eur_per_unit, units_per_eur, rate_date, source, basis FROM fx_rates
        WHERE ccy = :c AND rate_date > :d AND basis IN ('reference_daily', 'month_end', 'seed')
        ORDER BY rate_date ASC LIMIT 1
    """), {"c": ccy, "d": on_date}).mappings().first()
    if r:
        return {"currency": ccy, "rate": float(r["eur_per_unit"]), "units_per_eur": r["units_per_eur"] and float(r["units_per_eur"]),
                "rate_date": r["rate_date"].isoformat(), "source": r["source"], "basis": r["basis"],
                "age_days": (on_date - r["rate_date"]).days, "stale": True, "note": "no rate on or before the book date; the earliest later rate was used"}
    if ccy in FALLBACK_EUR_PER_UNIT:
        return {"currency": ccy, "rate": FALLBACK_EUR_PER_UNIT[ccy], "units_per_eur": None,
                "rate_date": _FALLBACK_DATE.isoformat(), "source": "fallback", "basis": "seed",
                "age_days": (on_date - _FALLBACK_DATE).days, "stale": True, "note": "offline fallback — not a live rate"}
    raise FxError(f"No FX rate for currency {ccy!r} — cannot convert to EUR")


def to_eur(session, amount: float, currency: Optional[str], on_date: Optional[date] = None) -> dict:
    """Convert `amount` in `currency` to EUR as of `on_date` → rate_for(...) plus {eur}. Raises FxError if unknown."""
    r = rate_for(session, currency, on_date)
    return {**r, "eur": round(float(amount) * r["rate"], 2)}


def supported_currencies(session) -> list[str]:
    """Currencies we can convert (every source ∪ pegs ∪ fallback), for UI validation."""
    rows = session.execute(text("SELECT DISTINCT ccy FROM fx_rates UNION SELECT ccy FROM fx_pegs")).scalars().all()
    return sorted(set(rows) | set(FALLBACK_EUR_PER_UNIT) | {"EUR"})


def coverage(session, on_date: Optional[date] = None) -> dict:
    """Every currency any country uses, plus every currency any source quotes: which source serves it on `on_date`, the
    kind of figure, its age, whether it is stale — and how closely the IMF agreed with the ECB where both quote it."""
    on_date = on_date or date.today()
    wanted = {r[0] for r in session.execute(text(
        "SELECT DISTINCT currency FROM ref_countries WHERE currency IS NOT NULL "
        "UNION SELECT DISTINCT ccy FROM fx_rates WHERE source <> 'seed' UNION SELECT ccy FROM fx_pegs")).all()}
    checks = {r["ccy"]: dict(r) for r in session.execute(text(
        "SELECT ccy, n_compared, median_pct, p95_pct, max_pct, verdict FROM fx_source_checks WHERE source = 'imf'")).mappings().all()}
    rows = []
    for c in sorted(wanted - {"EUR"}):
        try:
            r = rate_for(session, c, on_date)
            r = {k: r[k] for k in ("currency", "source", "basis", "units_per_eur", "rate_date", "age_days", "stale", "note")}
        except FxError:
            r = {"currency": c, "source": None, "basis": None, "units_per_eur": None, "rate_date": None, "age_days": None,
                 "stale": None, "note": "no source quotes this currency"}
        ck = checks.get(c)
        r["imf_vs_ecb"] = {k: (float(ck[k]) if k.endswith("_pct") else ck[k]) for k in
                           ("n_compared", "median_pct", "p95_pct", "max_pct", "verdict")} if ck else None
        rows.append(r)
    by = {}
    for r in rows:
        k = "none" if r["source"] is None else ("stale" if r["stale"] else r["source"])
        by[k] = by.get(k, 0) + 1
    return {"on_date": on_date.isoformat(), "summary": by, "currencies": rows}


def average_rate(session, currency: Optional[str], start: date, end: date) -> dict:
    """The EUR rate for a FLOW over a period (IAS 21: income, spend, premiums, revenue at the period average).

    Same result shape as rate_for, with basis 'period_average' and the period. In source order: a rate fixed by law
    for the whole period (exact); the mean of the ECB daily rates in the period (they must cover it: first within 10
    days of the start, last within 7 days of the end); the mean of the IMF monthly averages (the months may lag the
    end by up to 62 days). Otherwise the closing rate at the end is returned and marked stale — never a silent swap."""
    ccy = _norm_ccy(currency)
    if ccy == "EUR":
        return {"currency": "EUR", "rate": 1.0, "units_per_eur": 1.0, "rate_date": None, "source": "identity",
                "basis": "identity", "age_days": 0, "stale": False, "note": None}
    period = {"period_start": start.isoformat(), "period_end": end.isoformat()}
    p = session.execute(text("""
        SELECT units_per_eur, valid_from, legal_basis FROM fx_pegs
        WHERE ccy = :c AND valid_from <= :s AND (valid_to IS NULL OR valid_to >= :e) ORDER BY valid_from DESC LIMIT 1
    """), {"c": ccy, "s": start, "e": end}).mappings().first()
    if p:
        u = float(p["units_per_eur"])
        return {"currency": ccy, "rate": round(1.0 / u, 12), "units_per_eur": u, "rate_date": None, "source": "peg",
                "basis": "fixed_peg", "age_days": 0, "stale": False, "note": f"fixed — {p['legal_basis']}", **period}
    e = session.execute(text("""
        SELECT COUNT(*) AS n, AVG(units_per_eur) AS avg_u, MIN(rate_date) AS first, MAX(rate_date) AS last FROM fx_rates
        WHERE ccy = :c AND source = 'ecb' AND basis = 'reference_daily' AND rate_date BETWEEN :s AND :e
          AND units_per_eur IS NOT NULL
    """), {"c": ccy, "s": start, "e": end}).mappings().first()
    if e["n"] and (e["first"] - start).days <= 10 and (end - e["last"]).days <= 7:
        u = float(e["avg_u"])
        return {"currency": ccy, "rate": 1.0 / u, "units_per_eur": round(u, 6), "rate_date": e["last"].isoformat(),
                "source": "ecb", "basis": "period_average", "age_days": (end - e["last"]).days, "stale": False,
                "note": f"mean of {e['n']} ECB daily rates", **period}
    i = session.execute(text("""
        SELECT COUNT(*) AS n, AVG(units_per_eur) AS avg_u, MIN(rate_date) AS first, MAX(rate_date) AS last FROM fx_rates
        WHERE ccy = :c AND source = 'imf' AND basis = 'period_average' AND rate_date BETWEEN :s AND :e2
          AND units_per_eur IS NOT NULL
    """), {"c": ccy, "s": start, "e2": end}).mappings().first()
    months = (end.year - start.year) * 12 + end.month - start.month + 1
    if i["n"] and (i["first"] - start).days <= 31 and (end - i["last"]).days <= 62 and i["n"] >= months - 2:
        u = float(i["avg_u"])
        return {"currency": ccy, "rate": 1.0 / u, "units_per_eur": round(u, 6), "rate_date": i["last"].isoformat(),
                "source": "imf", "basis": "period_average", "age_days": (end - i["last"]).days, "stale": False,
                "note": f"mean of {i['n']} IMF monthly averages", **period}
    closing = rate_for(session, ccy, end)
    return {**closing, **period, "stale": True,
            "note": "no average rate covers the period; the closing rate was used" +
                    (f" ({closing['note']})" if closing.get("note") else "")}
