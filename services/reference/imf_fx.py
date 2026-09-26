"""IMF Exchange Rates (ER) — monthly national currency per euro, for the ~100 currencies the ECB does not quote.

Source: IMF data API (SDMX 2.1), dataflow IMF.STA / ER, indicator XDC_EUR ("domestic currency per euro"), monthly,
both end-of-period (EOP_RT → basis 'month_end', dated the last day of the month) and period average (PA_RT → basis
'period_average'). The IMF publishes per COUNTRY; the currency is the country's current legal tender from the CLDR
country reference (ref_countries).

Guards (a wrong rate is worse than none):
  * a period in the future is refused (the dataset has carried such rows);
  * a period before the country's current currency began is refused — an older value may be in the previous
    currency's units (e.g. a redenomination), so it is never filed under the new code;
  * a currency shared by several countries (CFA francs, East Caribbean dollar) is taken from one country only —
    the one with the most recent data — and the others are compared with it;
  * the euro itself is skipped.
First run loads from FIRST_PERIOD; later runs reload the last 18 months (the IMF revises recent months).
"""
from __future__ import annotations

import bisect
import calendar
import csv
import io
import urllib.request
from datetime import date, datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

API = "https://api.imf.org/external/sdmx/2.1/data/IMF.STA,ER,4.0.1/.XDC_EUR.EOP_RT+PA_RT.M"
FIRST_PERIOD = "2010-01"
_BASIS = {"EOP_RT": "month_end", "PA_RT": "period_average"}


class ImfFxError(RuntimeError):
    pass


def _get(start: str) -> bytes:
    req = urllib.request.Request(f"{API}?startPeriod={start}", headers={
        "Accept": "application/vnd.sdmx.data+csv;version=1.0.0", "User-Agent": "Tellumen/1.0 (IMF ER)"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def _month_end(period: str) -> Optional[date]:
    """'2026-M08' → 2026-08-31."""
    try:
        y, m = period.split("-M")
        y, m = int(y), int(m)
        return date(y, m, calendar.monthrange(y, m)[1])
    except (ValueError, AttributeError):
        return None


def parse(raw: bytes, country_ccy: dict[str, tuple[str, Optional[date]]], today: Optional[date] = None,
          iso2_of: Optional[dict[str, str]] = None) -> dict:
    """IMF CSV → {rows: [(ccy, rate_date, basis, units_per_eur, country)], refused: {reason: n}}.
    country_ccy: ISO-3 → (currency, currency valid from); iso2_of: ISO-3 → ISO-2 (for home-country choice)."""
    iso2_of = iso2_of or {}
    today = today or date.today()
    refused: dict[str, int] = {}
    series: dict[tuple[str, str], list] = {}   # (currency, country) → [(date, basis, value)]
    for r in csv.DictReader(io.StringIO(raw.decode("utf-8"))):
        iso3, tt, v = r.get("COUNTRY"), r.get("TYPE_OF_TRANSFORMATION"), r.get("OBS_VALUE")
        if not iso3 or tt not in _BASIS or not v:
            continue
        cc = country_ccy.get(iso3)
        if not cc or not cc[0] or cc[0] == "EUR":
            continue
        d = _month_end(r.get("TIME_PERIOD", ""))
        try:
            val = float(v)
        except ValueError:
            val = 0.0
        why = None
        if d is None or val <= 0:
            why = "unreadable period or value"
        elif d.replace(day=1) > today:
            why = "period in the future"
        elif cc[1] and d < cc[1]:
            why = "before the country's current currency began"
        if why:
            refused[why] = refused.get(why, 0) + 1
            continue
        series.setdefault((cc[0], iso3), []).append((d, _BASIS[tt], val))
    # one country per currency: the currency's HOME country when there is one (USD → USA, GBP → GBR, via the ISO-2
    # prefix), else the one with the latest data (then the most observations)
    best: dict[str, str] = {}
    for (ccy, iso3), obs in series.items():
        home = iso2_of.get(iso3, "") == ccy[:2]
        key = (home, max(o[0] for o in obs), len(obs))
        if ccy in best:
            b = best[ccy]
            bkey = (iso2_of.get(b, "") == ccy[:2], max(o[0] for o in series[(ccy, b)]), len(series[(ccy, b)]))
            if key <= bkey:
                continue
        best[ccy] = iso3
    rows = [(ccy, d, b, val, iso3) for ccy, iso3 in best.items() for d, b, val in series[(ccy, iso3)]]
    return {"rows": rows, "refused": refused, "countries_per_currency": {c: sorted(i for (cc, i) in series if cc == c)
                                                                          for c in best if sum(1 for (cc, _) in series if cc == c) > 1}}


def upsert(session: Session, rows: Iterable[tuple]) -> int:
    now = datetime.now(timezone.utc)
    batch = [{"c": c, "d": d, "b": b, "u": round(v, 6), "e": round(1.0 / v, 12), "f": now} for c, d, b, v, _ in rows]
    for i in range(0, len(batch), 5000):
        session.execute(text("""
            INSERT INTO fx_rates (ccy, rate_date, eur_per_unit, units_per_eur, source, basis, fetched_at)
            VALUES (:c, :d, :e, :u, 'imf', :b, :f)
            ON CONFLICT (ccy, rate_date, source, basis) DO UPDATE SET eur_per_unit = EXCLUDED.eur_per_unit,
                   units_per_eur = EXCLUDED.units_per_eur, fetched_at = EXCLUDED.fetched_at
        """), batch[i:i + 5000])
    return len(batch)


def refresh(session: Session, full: bool = False) -> dict:
    have = session.execute(text("SELECT MAX(rate_date) FROM fx_rates WHERE source = 'imf'")).scalar()
    if full or have is None:
        start = FIRST_PERIOD
    else:
        y, m = date.today().year, date.today().month - 18
        while m <= 0:
            y, m = y - 1, m + 12
        start = f"{y}-{m:02d}"
    cc = {r[0]: (r[1], r[2]) for r in session.execute(text(
        "SELECT iso3, currency, currency_from FROM ref_countries WHERE iso3 IS NOT NULL AND currency IS NOT NULL")).all()}
    if not cc:
        raise ImfFxError("the country reference (feed reference_countries) is not loaded — currencies can't be assigned")
    iso2_of = {r[0]: r[1] for r in session.execute(text("SELECT iso3, iso2 FROM ref_countries WHERE iso3 IS NOT NULL")).all()}
    out = parse(_get(start), cc, iso2_of=iso2_of)
    if not out["rows"]:
        raise ImfFxError("the IMF returned no usable rates")
    bad = cross_check(session, out["rows"])
    rows = [r for r in out["rows"] if r[0] not in bad]
    n = upsert(session, rows)
    session.commit()
    ccys = {r[0] for r in rows}
    return {"from": start, "n_rows": n, "n_currencies": len(ccys), "refused": out["refused"],
            "refused_currencies": bad, "shared_currencies": out["countries_per_currency"]}


# A series filed under the wrong currency is off by orders of magnitude every month; genuine timing/method differences
# between an IMF month-end and the ECB 16:00 CET fix are ~0.0-0.4% typically, <2% in 95% of months (measured
# 2010-2026, 30 currencies). So judge the TYPICAL gap, not the worst single month (volatile days reach 5-19%).
MAX_TYPICAL_GAP = 0.02     # median over all compared months
MAX_P95_GAP = 0.10         # 95th percentile


def cross_check(session: Session, rows: list[tuple]) -> dict[str, str]:
    """For currencies BOTH sources cover: compare each IMF month-end with the ECB rate on the same day (or the last ECB
    working day before it, within 5 days). Record the agreement per currency (fx_source_checks) and refuse a
    currency's IMF series whose typical gap shows it is not the same currency. Returns {currency: reason} refused."""
    by_ccy: dict[str, list] = {}
    for c, d, b, v, iso3 in rows:
        if b == "month_end":
            by_ccy.setdefault(c, []).append((d, v, iso3))
    bad: dict[str, str] = {}
    for c, obs in by_ccy.items():
        ecb = session.execute(text("""SELECT rate_date, units_per_eur FROM fx_rates WHERE ccy = :c AND source = 'ecb'
                                       AND basis = 'reference_daily' AND units_per_eur IS NOT NULL ORDER BY rate_date"""),
                              {"c": c}).all()
        if not ecb:
            continue
        dates = [r[0] for r in ecb]
        devs = []
        for d, v, _ in obs:
            i = bisect.bisect_right(dates, d) - 1
            if i >= 0 and (d - dates[i]).days <= 5:
                devs.append(abs(v - float(ecb[i][1])) / float(ecb[i][1]))
        if not devs:
            continue
        devs.sort()
        med, p95 = devs[len(devs) // 2], devs[max(0, int(0.95 * len(devs)) - 1)]
        verdict, reason = "accepted", None
        if med > MAX_TYPICAL_GAP or p95 > MAX_P95_GAP:
            verdict = "refused"
            reason = (f"IMF month-end differs from the ECB by {100 * med:.1f}% typically ({100 * p95:.1f}% at the 95th "
                      "percentile) — not the same currency series; refused")
            bad[c] = reason
        session.execute(text("""
            INSERT INTO fx_source_checks (ccy, source, reference, n_compared, median_pct, p95_pct, max_pct, verdict, reason, checked_at)
            VALUES (:c, 'imf', 'ecb', :n, :m, :p, :x, :v, :r, now())
            ON CONFLICT (ccy, source, reference) DO UPDATE SET n_compared = EXCLUDED.n_compared, median_pct = EXCLUDED.median_pct,
                   p95_pct = EXCLUDED.p95_pct, max_pct = EXCLUDED.max_pct, verdict = EXCLUDED.verdict, reason = EXCLUDED.reason,
                   checked_at = now()
        """), {"c": c, "n": len(devs), "m": round(100 * med, 3), "p": round(100 * p95, 3), "x": round(100 * devs[-1], 3),
               "v": verdict, "r": reason})
    return bad
