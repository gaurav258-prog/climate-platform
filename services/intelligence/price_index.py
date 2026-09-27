"""Commodity & farm-input price indices — observed authoritative market data (FAO / World Bank / USDA),
wired into the sourcing book as INPUT-COST PRESSURE.

Tellumen never forecasts a price (the buyer supplies their own price view). What it can add is the OBSERVED
agency index and what a move in it means for THIS book: for a buyer, a commodity whose index has RISEN since a
trailing baseline is input-cost pressure on the bill of materials, weighted by the spend actually exposed to it.
Honest by construction — a commodity with no index loaded is shown as 'no index', never guessed; the pressure is
observed-price-driven, not a projection.

Currency (multi-currency phase 4, 2026-09-27): every series states the currency it is quoted in (World Bank / USDA in
US dollars, the EU agri-food portal in euro). The move is measured in the BUYER's currency — each month's quote is
converted at that month's average rate before the latest month is compared with the baseline — so a euro buyer sees
the dollar price move AND the dollar's own move. Both parts are reported. A series whose currency is unknown, or a
month without a rate, is reported as not usable, never assumed to be in the buyer's currency.
"""
from __future__ import annotations

import calendar
import uuid
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.reference.fx import FxError, average_rate

BASELINE_MONTHS = 12   # trailing window the latest index is compared against


def currency_of(unit: Optional[str], source: Optional[str]) -> Optional[str]:
    """The currency a series is quoted in, from what its publisher says — the same rules the backfill used."""
    u, s = (unit or "").strip().lower(), (source or "").strip().lower()
    if u.startswith(("$", "usd", "us$")):
        return "USD"
    if u.startswith(("€", "eur")):
        return "EUR"
    if s.startswith("eu commission"):
        return "EUR"
    if s.startswith(("world bank", "usda")):
        return "USD"
    return None


def ingest(session: Session, rows: list[dict]) -> dict:
    """Upsert reference index rows. rows: {source, commodity, period_ym 'YYYY-MM', index_value, unit?, currency?}.
    A row whose currency is neither given nor readable from its unit / publisher is refused with the reason."""
    from services.reference.fx import supported_currencies
    known = set(supported_currencies(session))
    n, refused = 0, []
    for i, r in enumerate(rows, start=1):
        commodity = str(r.get("commodity") or "").strip().lower()
        period = str(r.get("period_ym") or "").strip()
        try:
            val = float(str(r.get("index_value")).replace(",", "").strip())
        except (TypeError, ValueError, AttributeError):
            refused.append({"row": i, "reason": "index_value is not a number"})
            continue
        if not commodity or len(period) != 7:
            refused.append({"row": i, "reason": "commodity and period_ym (YYYY-MM) are required"})
            continue
        ccy = (str(r.get("currency") or "").strip().upper() or currency_of(r.get("unit"), r.get("source")))
        if not ccy or ccy not in known:
            refused.append({"row": i, "reason": "currency is required (ISO code the series is quoted in, e.g. USD)"
                            if not ccy else f"'{ccy}' is not a currency we can convert"})
            continue
        session.execute(text("""
            INSERT INTO commodity_price_index (price_id, source, commodity, period_ym, index_value, unit, currency)
            VALUES (CAST(:i AS uuid), :s, :c, :p, :v, :u, :ccy)
            ON CONFLICT (source, commodity, period_ym) DO UPDATE SET index_value = EXCLUDED.index_value, unit = EXCLUDED.unit,
                   currency = EXCLUDED.currency, ingested_at = now()
        """), {"i": str(uuid.uuid4()), "s": str(r.get("source") or "sample")[:60], "c": commodity[:60],
               "p": period, "v": val, "u": str(r.get("unit") or "")[:40] or None, "ccy": ccy})
        n += 1
    session.commit()
    return {"rows": n, "n_refused": len(refused), "refused": refused[:50]}


def _month(ym: str) -> tuple[date, date]:
    y, m = int(ym[:4]), int(ym[5:7])
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def _shock(session: Session, commodity: str, buyer_ccy: str = "EUR") -> Optional[dict]:
    """Latest month vs the mean of the prior BASELINE_MONTHS, in the buyer's currency — the observed % move, split into
    the move in the quote currency and the currency's own move. One series only (the most recently updated), never a
    mix of publishers. None if no data; {"usable": False, "reason"} if it can't be put in the buyer's currency."""
    src = session.execute(text("""
        SELECT source FROM commodity_price_index WHERE commodity = :c ORDER BY period_ym DESC, ingested_at DESC LIMIT 1
    """), {"c": commodity.lower()}).scalar()
    if src is None:
        return None
    rows = session.execute(text("""
        SELECT period_ym, CAST(index_value AS FLOAT) AS v, source, unit, currency
        FROM commodity_price_index WHERE commodity = :c AND source = :s ORDER BY period_ym DESC LIMIT :n
    """), {"c": commodity.lower(), "s": src, "n": BASELINE_MONTHS + 1}).mappings().all()
    latest = rows[0]
    q = (latest["currency"] or "").strip() or None
    base = {"commodity": commodity, "latest_period": latest["period_ym"], "source": latest["source"], "unit": latest["unit"],
            "quote_currency": q, "currency": buyer_ccy}
    if q is None:
        return {**base, "usable": False, "reason": "the series does not say which currency it is quoted in"}

    def move(vals: list[float]) -> float:
        prior = vals[1:]
        baseline = sum(prior) / len(prior) if prior else vals[0]
        return 100 * (vals[0] - baseline) / baseline if baseline else 0.0

    local = [r["v"] for r in rows]
    if q == buyer_ccy:
        buyer = local
    else:
        buyer = []
        for r in rows:          # each month at its own average rate: buyer units = quote units × (buyer/EUR) / (quote/EUR)
            s, e = _month(r["period_ym"])
            try:
                qr, br = average_rate(session, q, s, e), average_rate(session, buyer_ccy, s, e)
            except FxError:
                return {**base, "usable": False, "reason": f"no {q}→{buyer_ccy} rate for {r['period_ym']}"}
            buyer.append(r["v"] * br["units_per_eur"] / qr["units_per_eur"])
    shock, local_move = move(buyer), move(local)
    return {**base, "usable": True, "latest_index": round(local[0], 2), "baseline_index": round(sum(local[1:]) / max(len(local) - 1, 1), 2),
            "shock_pct": round(shock, 2), "price_move_pct": round(local_move, 2),
            "currency_effect_pct": round(shock - local_move, 2) if q != buyer_ccy else 0.0}


def book_price_pressure(session: Session, org_id: str) -> dict:
    """Input-cost pressure on the sourcing book from OBSERVED price moves: spend × the positive move measured in the
    buyer's currency (the organisation's presentation currency), per commodity. A commodity with no usable index is
    reported as uncovered (never guessed)."""
    from services.governance.reporting_settings import get_settings
    from services.reference.fx import rate_for
    ccy = get_settings(session, org_id)["presentation_currency"]
    plots = session.execute(text("""
        SELECT co.name AS commodity, SUM(CAST(p.annual_spend_eur AS FLOAT)) AS spend
        FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id = p.commodity_id
        WHERE p.org_id = CAST(:o AS uuid) GROUP BY co.name
    """), {"o": org_id}).mappings().all()
    if not plots:
        return {"available": False, "reason": "no_sourcing_book"}
    # spend is held in EUR; in another presentation currency it is shown at today's closing rate
    to_ccy = 1.0 if ccy == "EUR" else rate_for(session, ccy)["units_per_eur"]
    items, total_spend, pressure, covered_spend = [], 0.0, 0.0, 0.0
    for pl in plots:
        spend = (pl["spend"] or 0) * to_ccy
        total_spend += spend
        sh = _shock(session, pl["commodity"], ccy)
        if sh is None or not sh["usable"]:
            items.append({"commodity": pl["commodity"], "spend_eur": round(spend), "covered": False,
                          "shock_pct": None, "pressure_eur": 0, "reason": (sh or {}).get("reason") or "no index loaded"})
            continue
        covered_spend += spend
        p = spend * max(0.0, sh["shock_pct"]) / 100.0
        pressure += p
        items.append({"commodity": pl["commodity"], "spend_eur": round(spend), "covered": True,
                      "shock_pct": sh["shock_pct"], "price_move_pct": sh["price_move_pct"],
                      "currency_effect_pct": sh["currency_effect_pct"], "quote_currency": sh["quote_currency"],
                      "latest_period": sh["latest_period"], "source": sh["source"], "pressure_eur": round(p)})
    items.sort(key=lambda x: x["pressure_eur"], reverse=True)
    return {
        "available": True, "currency": ccy,
        "summary": {
            "total_spend_eur": round(total_spend), "covered_spend_eur": round(covered_spend),
            "coverage_pct": round(100 * covered_spend / total_spend, 1) if total_spend else 0,
            "input_cost_pressure_eur": round(pressure),
            "pressure_pct_of_spend": round(100 * pressure / total_spend, 2) if total_spend else 0,
        },
        "commodities": items,
        "note": (f"Amounts in {ccy} (fields keep their *_eur names). Each price move is measured in {ccy}: a series quoted "
                 f"in another currency is converted month by month at that month's average rate, so the move includes "
                 f"the currency's own move (shown separately)."),
    }
