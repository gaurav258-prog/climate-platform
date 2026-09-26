"""Money in any currency → EUR, at the book date, by the agreed rate policy — for every sector's intake.

Agreed 2026-09-26:
  * an amount's currency is never assumed: it is the field's own currency from the mapping, else the row's `currency`
    column, else the currency DECLARED for the batch (upload form, API body, drop-folder channel). None → refused;
  * the rate is the one for the BOOK DATE the figures describe: the row's `book_date` column, else the batch's;
  * a BALANCE (values, exposures, sums insured, EVIC) converts at the CLOSING rate on the book date; a FLOW (annual
    income, spend, revenue — `flow` in the field catalogue) at the AVERAGE rate of the 12 months to the book date;
  * every rate used is reported (source, kind, date, age); a stale one is a failed check (4-eyes); a currency with
    no rate at all refuses the row, with the reason. The original amounts are kept with the staged row.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from services.ingest.batch_controls import parse_money
from services.intake.values import is_blank
from services.reference.fx import FxError, average_rate, rate_for

FLOW_PERIOD_DAYS = 365
_HIDDEN = "__ccy__"            # a mapping's per-field currency column travels in the frame under this prefix


class MoneyError(ValueError):
    pass


def hidden_column(field: str) -> str:
    return f"{_HIDDEN}{field}"


def parse_book_date(v) -> Optional[date]:
    if is_blank(v):
        return None
    try:
        return date.fromisoformat(str(v).strip()[:10])
    except ValueError:
        return None


def convert(session: Session, df: pd.DataFrame, specs: list[dict], ctx: dict) -> tuple[pd.DataFrame, dict, dict, dict]:
    """ctx: {currency: declared batch currency or None, book_date: date or None, field_currency: {field: 'USD'}}.
    Returns (frame with EUR amounts, report, problems {row index: [msg]}, natives {row index: {field: [amount, ccy]}})."""
    out = df.copy()
    money = [s for s in specs if s.get("kind") == "money" and s["name"] in out.columns]
    for s in money:                                    # a whole-number column must be able to take a converted amount
        out[s["name"]] = out[s["name"]].astype(object)
    fixed = ctx.get("field_currency") or {}
    declared, bdate = ctx.get("currency"), ctx.get("book_date")
    rates: dict[tuple, dict] = {}
    problems: dict = {}
    natives: dict = {}
    n_conv = 0

    def rate(ccy: str, d: date, flow: bool) -> dict:
        key = (ccy, d, flow)
        if key not in rates:
            rates[key] = (average_rate(session, ccy, d - timedelta(days=FLOW_PERIOD_DAYS - 1), d) if flow
                          else rate_for(session, ccy, d))
        return rates[key]

    row_ccy = out["currency"] if "currency" in out.columns else None
    row_date = out["book_date"] if "book_date" in out.columns else None
    for idx in out.index:
        d = parse_book_date(row_date[idx]) if row_date is not None else None
        if d is not None and d > date.today():
            problems.setdefault(idx, []).append(f"book date {d} is in the future")
            continue
        d = d or bdate
        for s in money:
            f = s["name"]
            amt = parse_money(out.at[idx, f])
            if amt is None:
                continue                                   # blank or unreadable: validation reports it
            hid = hidden_column(f)
            ccy = (fixed.get(f) or (None if hid not in out.columns or is_blank(out.at[idx, hid]) else str(out.at[idx, hid]).strip())
                   or (None if row_ccy is None or is_blank(row_ccy[idx]) else str(row_ccy[idx]).strip()) or declared)
            if not ccy:
                problems.setdefault(idx, []).append(f"{s.get('label', f)}: no currency — declare the file's currency or add a currency column")
                continue
            ccy = ccy.upper()
            natives.setdefault(idx, {})[f] = [amt, ccy]
            if ccy == "EUR":
                continue
            if d is None:
                problems.setdefault(idx, []).append(f"{s.get('label', f)}: no book date to convert {ccy} — declare it or add a book_date column")
                continue
            try:
                r = rate(ccy, d, bool(s.get("flow")))
            except FxError:
                problems.setdefault(idx, []).append(f"{s.get('label', f)}: no exchange rate for {ccy}")
                continue
            out.at[idx, f] = round(amt * r["rate"], 2)
            n_conv += 1
    out = out[[c for c in out.columns if not c.startswith(_HIDDEN)]]

    used = []
    for (ccy, d, flow), r in sorted(rates.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
        used.append({"currency": ccy, "book_date": d.isoformat(), "policy": "average" if flow else "closing",
                     **{k: r.get(k) for k in ("units_per_eur", "source", "basis", "rate_date", "age_days", "stale", "note",
                                              "period_start", "period_end")}})
    currencies = sorted({v[1] for n in natives.values() for v in n.values()})
    report = {"declared_currency": declared, "book_date": bdate.isoformat() if bdate else None, "currencies": currencies,
              "n_converted": n_conv, "rates": used, "n_rows_refused": len(problems),
              "warnings": [f"{u['currency']} {u['policy']} rate for {u['book_date']}: {u['note']}" for u in used if u["stale"]]}
    return out, report, problems, natives


def gate_reason(report: Optional[dict]) -> Optional[str]:
    if not report or not report.get("warnings"):
        return None
    w = report["warnings"]
    return f"Currency: {len(w)} stale rate(s) — {'; '.join(w[:3])}{'; …' if len(w) > 3 else ''}."


def validate_declaration(session: Session, currency: Optional[str], book_date: Optional[str]) -> tuple[Optional[str], Optional[date]]:
    """Check what the sender declared for the batch. Both may be absent (then each row must carry its own)."""
    from services.reference.fx import supported_currencies
    ccy = (currency or "").strip().upper() or None
    if ccy and ccy not in set(supported_currencies(session)):
        raise MoneyError(f"'{ccy}' is not a currency we can convert (ISO 4217 code, e.g. EUR, USD, GBP).")
    d = None
    if book_date not in (None, ""):
        d = parse_book_date(book_date)
        if d is None:
            raise MoneyError("The book date must be YYYY-MM-DD.")
        if d > date.today():
            raise MoneyError("The book date can't be in the future — it is the date your figures describe.")
    return ccy, d


def batch_context(session: Session, df: pd.DataFrame, specs: list[dict], mapping_report: Optional[dict],
                  currency: Optional[str], book_date) -> dict:
    """The batch's money context, checked up front: a currency must be declared unless every money field has its own
    (a mapping's per-field currency) or the file has a currency column; a book date must be declared unless the file
    has a book_date column. Raises MoneyError with what to do."""
    ccy, d = validate_declaration(session, currency, book_date if not isinstance(book_date, date) else book_date.isoformat())
    field_ccy = (mapping_report or {}).get("field_currency") or {}
    money_fields = [s["name"] for s in specs if s.get("kind") == "money" and s["name"] in df.columns]
    uncovered = [f for f in money_fields if f not in field_ccy and hidden_column(f) not in df.columns]
    if uncovered and not ccy and "currency" not in df.columns:
        raise MoneyError("Say which currency the amounts are in — choose it for the file, or add a currency column.")
    if d is None and "book_date" not in df.columns:
        raise MoneyError("Say which date the figures describe (the book date) — enter it for the file, or add a "
                         "book_date column. Amounts are converted at that date's rates.")
    return {"currency": ccy, "book_date": d, "field_currency": field_ccy}


# ── single amounts: every money input outside the intake pipeline (GL, arrears, sites, plots, losses, funds) ──

def convert_amount(session: Session, amount, currency: Optional[str], book_date, *, flow: bool = False,
                   period: Optional[tuple[date, date]] = None, label: str = "amount") -> dict:
    """One amount in any currency → {eur, native, currency, rate}. Same rules as a batch: the currency must be given
    (never assumed); a balance converts at the closing rate on the book date; a flow at the average over `period`
    (default: the 12 months to the book date). Raises MoneyError with what to do."""
    amt = parse_money(amount) if not isinstance(amount, (int, float)) else float(amount)
    if amt is None:
        raise MoneyError(f"{label} is not a number")
    ccy = (currency or "").strip().upper()
    if not ccy:
        raise MoneyError(f"{label}: say which currency it is in")
    d = book_date if isinstance(book_date, date) else parse_book_date(book_date)
    if d is None and period is None:
        raise MoneyError(f"{label}: say which date it describes (the book date)")
    if d is not None and d > date.today():
        raise MoneyError(f"{label}: the book date {d} is in the future")
    if ccy == "EUR":
        return {"eur": round(amt, 2), "native": amt, "currency": "EUR", "rate": None}
    try:
        if flow:
            start, end = period or (d - timedelta(days=FLOW_PERIOD_DAYS - 1), d)
            r = average_rate(session, ccy, start, end)
        else:
            r = rate_for(session, ccy, d)
    except FxError:
        raise MoneyError(f"{label}: no exchange rate for {ccy}")
    rate = {"currency": ccy, "policy": "average" if flow else "closing",
            **{k: r.get(k) for k in ("units_per_eur", "source", "basis", "rate_date", "stale", "note", "period_start", "period_end")}}
    return {"eur": round(amt * r["rate"], 2), "native": amt, "currency": ccy, "rate": rate}


def source_record(currency: str, book_date, converted: dict[str, dict]) -> dict:
    """The money_source JSON stored beside the converted amounts: what was sent, and the rates used."""
    return {"currency": currency, "book_date": book_date.isoformat() if isinstance(book_date, date) else book_date,
            "native": {f: c["native"] for f, c in converted.items()},
            "rates": [c["rate"] for c in converted.values() if c.get("rate")]}
