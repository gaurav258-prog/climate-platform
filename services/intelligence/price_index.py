"""Commodity & farm-input price indices — observed authoritative market data (FAO / World Bank / USDA),
wired into the sourcing book as INPUT-COST PRESSURE.

Tellumen never forecasts a price (the buyer supplies their own price view). What it can add is the OBSERVED
agency index and what a move in it means for THIS book: for a buyer, a commodity whose index has RISEN since a
trailing baseline is input-cost pressure on the bill of materials, weighted by the spend actually exposed to it.
Honest by construction — a commodity with no index loaded is shown as 'no index', never guessed; the pressure is
observed-price-driven, not a projection.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

BASELINE_MONTHS = 12   # trailing window the latest index is compared against


def ingest(session: Session, rows: list[dict]) -> dict:
    """Upsert reference index rows. rows: {source, commodity, period_ym 'YYYY-MM', index_value, unit?}."""
    n = 0
    for r in rows:
        commodity = str(r.get("commodity") or "").strip().lower()
        period = str(r.get("period_ym") or "").strip()
        try:
            val = float(str(r.get("index_value")).replace(",", "").strip())
        except (TypeError, ValueError, AttributeError):
            continue
        if not commodity or len(period) != 7:
            continue
        session.execute(text("""
            INSERT INTO commodity_price_index (price_id, source, commodity, period_ym, index_value, unit)
            VALUES (CAST(:i AS uuid), :s, :c, :p, :v, :u)
            ON CONFLICT (source, commodity, period_ym) DO UPDATE SET index_value = EXCLUDED.index_value, unit = EXCLUDED.unit, ingested_at = now()
        """), {"i": str(uuid.uuid4()), "s": str(r.get("source") or "sample")[:60], "c": commodity[:60],
               "p": period, "v": val, "u": str(r.get("unit") or "")[:40] or None})
        n += 1
    session.commit()
    return {"rows": n}


def _shock(session: Session, commodity: str) -> Optional[dict]:
    """Latest index vs the mean of the prior BASELINE_MONTHS — the observed % move. None if no data."""
    rows = session.execute(text("""
        SELECT period_ym, CAST(index_value AS FLOAT) AS v, source, unit
        FROM commodity_price_index WHERE commodity = :c ORDER BY period_ym DESC LIMIT :n
    """), {"c": commodity.lower(), "n": BASELINE_MONTHS + 1}).mappings().all()
    if not rows:
        return None
    latest = rows[0]
    prior = [r["v"] for r in rows[1:]]
    baseline = sum(prior) / len(prior) if prior else latest["v"]
    shock = round(100 * (latest["v"] - baseline) / baseline, 2) if baseline else 0.0
    return {"commodity": commodity, "latest_period": latest["period_ym"], "latest_index": round(latest["v"], 2),
            "baseline_index": round(baseline, 2), "shock_pct": shock, "source": latest["source"], "unit": latest["unit"]}


def book_price_pressure(session: Session, org_id: str) -> dict:
    """Input-cost pressure on the sourcing book from OBSERVED price moves: spend × the positive index shock,
    per commodity. A commodity with no loaded index is reported as uncovered (never guessed)."""
    plots = session.execute(text("""
        SELECT co.name AS commodity, SUM(CAST(p.annual_spend_eur AS FLOAT)) AS spend
        FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id = p.commodity_id
        WHERE p.org_id = CAST(:o AS uuid) GROUP BY co.name
    """), {"o": org_id}).mappings().all()
    if not plots:
        return {"available": False, "reason": "no_sourcing_book"}
    items, total_spend, pressure, covered_spend = [], 0.0, 0.0, 0.0
    for pl in plots:
        spend = pl["spend"] or 0
        total_spend += spend
        sh = _shock(session, pl["commodity"])
        if sh is None:
            items.append({"commodity": pl["commodity"], "spend_eur": round(spend), "covered": False,
                          "shock_pct": None, "pressure_eur": 0})
            continue
        covered_spend += spend
        p = spend * max(0.0, sh["shock_pct"]) / 100.0
        pressure += p
        items.append({"commodity": pl["commodity"], "spend_eur": round(spend), "covered": True,
                      "shock_pct": sh["shock_pct"], "latest_period": sh["latest_period"], "source": sh["source"],
                      "pressure_eur": round(p)})
    items.sort(key=lambda x: x["pressure_eur"], reverse=True)
    return {
        "available": True,
        "summary": {
            "total_spend_eur": round(total_spend), "covered_spend_eur": round(covered_spend),
            "coverage_pct": round(100 * covered_spend / total_spend, 1) if total_spend else 0,
            "input_cost_pressure_eur": round(pressure),
            "pressure_pct_of_spend": round(100 * pressure / total_spend, 2) if total_spend else 0,
        },
        "commodities": items,
    }
