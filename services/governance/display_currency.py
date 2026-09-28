"""The currency the organisation's screens show money in (multi-currency phase 5).

The engine keeps every amount in EUR (intake converts at the book date — phase 1). A live screen shows it in the
organisation's presentation currency (reporting settings), translated by the SAME rate policy a filing uses
(translation.py, IAS 21.39): balances at the latest closing rate, flows (annual expected loss, premiums, revenue, spend)
at the average of the last 12 months — or at closing where the governed `fx_flow_rate` says so. The organisation's own
rates are used where it supplied them within tolerance (intake.money._choose). A frozen filing never uses this: it
presents at its own period-end rates, recorded on the snapshot.

When the presentation currency is EUR nothing is translated. A currency with no rate anywhere falls back to EUR and
says why — the amounts are never relabelled.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from services.reference.fx import FxError

ENGINE_CURRENCY = "EUR"
FLOW_PERIOD_DAYS = 365


def _units(r: dict) -> float:
    u = r.get("units_per_eur")
    return float(u) if u else 1.0 / float(r["rate"])


def _rate(r: dict) -> dict:
    return {"units_per_eur": round(_units(r), 8), "rate_date": r.get("rate_date"), "source": r.get("source"),
            "basis": r.get("basis"), "stale": bool(r.get("stale")), "note": r.get("note"),
            "period_start": r.get("period_start"), "period_end": r.get("period_end")}


def view(session: Session, org_id: str, on: Optional[date] = None) -> dict:
    """{currency, engine_currency, balance, flow, flow_policy, note} — balance / flow: units of `currency` per EUR."""
    from services.governance.reporting_settings import get_settings
    from services.intake.money import _choose, rate_policy
    on = on or date.today()
    pres = (get_settings(session, org_id).get("presentation_currency") or ENGINE_CURRENCY).upper()
    policy = rate_policy(session, org_id)["flow"]
    identity = {"units_per_eur": 1.0, "rate_date": None, "source": "identity", "basis": "identity", "stale": False,
                "note": None, "period_start": None, "period_end": None}
    out = {"currency": pres, "engine_currency": ENGINE_CURRENCY, "flow_policy": policy, "as_of": on.isoformat(),
           "balance": identity, "flow": identity, "note": None}
    if pres == ENGINE_CURRENCY:
        return out
    try:
        bal = _rate(_choose(session, org_id, pres, on, False, None))
        fl = bal if policy == "closing" else \
            _rate(_choose(session, org_id, pres, on, True, (on - timedelta(days=FLOW_PERIOD_DAYS - 1), on)))
    except FxError as e:
        return {**out, "currency": ENGINE_CURRENCY,
                "note": f"No exchange rate for {pres} ({e}) — amounts are shown in EUR, the engine's currency."}
    return {**out, "balance": bal, "flow": fl}


# ── writing an engine amount in the organisation's currency (server-side text: task feed, board pack, KRI hints) ──
# Set once per request by the entry point (using()); a formatter called without a view writes EUR, untranslated.
_current: ContextVar[Optional[dict]] = ContextVar("display_view", default=None)


@contextmanager
def using(session: Session, org_id: str, dv: Optional[dict] = None):
    token = _current.set(dv or view(session, org_id))
    try:
        yield _current.get()
    finally:
        _current.reset(token)


def _write(v, dv: Optional[dict], kind: str, compact: bool) -> str:
    from services.governance.money_format import money
    dv = dv or _current.get()
    if not isinstance(v, (int, float)):
        return "—"
    if not dv:
        return money(v, ENGINE_CURRENCY, compact)
    return money(float(v) * dv[kind]["units_per_eur"], dv["currency"], compact)


def balance(v, dv: Optional[dict] = None, compact: bool = True) -> str:
    """An engine (EUR) balance in the organisation's currency, at the closing rate."""
    return _write(v, dv, "balance", compact)


def flow(v, dv: Optional[dict] = None, compact: bool = True) -> str:
    """An engine (EUR) yearly flow in the organisation's currency, at the average rate."""
    return _write(v, dv, "flow", compact)
