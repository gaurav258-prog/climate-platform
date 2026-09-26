"""ECB euro foreign exchange reference rates — fetched directly from the European Central Bank.

    first run (or a gap longer than 90 days) → eurofxref-hist.zip   every published day since 4 Jan 1999
    every day after                          → eurofxref-hist-90d.xml  the last 90 days: heals any missed days

The ECB publishes around 16:00 CET on TARGET working days (no weekend or holiday rates). We store its figure exactly
as published (units of currency per 1 EUR) and the inverse conversions multiply by. A refresh whose newest ECB date
is more than MAX_AGE_DAYS old fails loudly: the feed monitor shows it red, and it is never recorded as fresh.
"""
from __future__ import annotations

import csv
import io
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime, timezone
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

HIST_ZIP = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"
HIST_90D = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"
MAX_AGE_DAYS = 5          # a long weekend + a holiday; older than this, the ECB data we hold is stale
_NS = {"e": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}


class EcbFxError(RuntimeError):
    pass


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Tellumen/1.0 (ECB reference rates)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def parse_hist_csv(raw: bytes) -> Iterable[tuple[str, str, float]]:
    """eurofxref-hist.csv → (date, currency, units_per_eur). 'N/A' (currency not quoted that day) is skipped."""
    rows = csv.reader(io.StringIO(raw.decode("utf-8")))
    header = [h.strip() for h in next(rows)]
    for r in rows:
        if not r or not r[0].strip():
            continue
        d = r[0].strip()
        for ccy, v in zip(header[1:], r[1:]):
            v = v.strip()
            if ccy and v and v != "N/A":
                yield d, ccy, float(v)


def parse_xml(raw: bytes) -> Iterable[tuple[str, str, float]]:
    """eurofxref-*.xml → (date, currency, units_per_eur)."""
    root = ET.fromstring(raw)
    for day in root.iterfind(".//e:Cube[@time]", _NS):
        d = day.get("time")
        for c in day.iterfind("e:Cube[@currency]", _NS):
            yield d, c.get("currency"), float(c.get("rate"))


def upsert(session: Session, rows: Iterable[tuple[str, str, float]]) -> dict:
    now = datetime.now(timezone.utc)
    batch = [{"c": ccy, "d": d, "u": round(u, 6), "e": round(1.0 / u, 8), "f": now} for d, ccy, u in rows if u > 0]
    for i in range(0, len(batch), 5000):
        session.execute(text("""
            INSERT INTO fx_rates (ccy, rate_date, eur_per_unit, units_per_eur, source, fetched_at)
            VALUES (:c, CAST(:d AS date), :e, :u, 'ecb', :f)
            ON CONFLICT (ccy, rate_date) DO UPDATE SET eur_per_unit = EXCLUDED.eur_per_unit,
                   units_per_eur = EXCLUDED.units_per_eur, source = 'ecb', fetched_at = EXCLUDED.fetched_at
        """), batch[i:i + 5000])
    dates = sorted({b["d"] for b in batch})
    return {"n_rows": len(batch), "n_days": len(dates), "from": dates[0] if dates else None, "to": dates[-1] if dates else None,
            "currencies": sorted({b["c"] for b in batch})}


def latest_ecb_date(session: Session):
    return session.execute(text("SELECT MAX(rate_date) FROM fx_rates WHERE source = 'ecb'")).scalar()


def refresh(session: Session, full: bool = False) -> dict:
    """Pull from the ECB and store. Full history when asked, when we hold no ECB rows, or when the gap exceeds the
    90-day file; otherwise the 90-day file. Raises EcbFxError if the newest ECB date is still stale afterwards."""
    last = latest_ecb_date(session)
    use_full = full or last is None or (date.today() - last).days > 85
    raw = _get(HIST_ZIP) if use_full else _get(HIST_90D)
    if use_full:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            rows = list(parse_hist_csv(z.read(z.namelist()[0])))
    else:
        rows = list(parse_xml(raw))
    if not rows:
        raise EcbFxError("the ECB file contained no rates")
    out = upsert(session, rows)
    session.commit()
    newest = latest_ecb_date(session)
    age = (date.today() - newest).days
    out.update({"source": HIST_ZIP if use_full else HIST_90D, "newest": newest.isoformat(), "age_days": age})
    if age > MAX_AGE_DAYS:
        raise EcbFxError(f"newest ECB rate is from {newest} ({age} days old) — the ECB file has not updated")
    return out
