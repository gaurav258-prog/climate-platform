"""A filing's money in the filing's own currency — solo in the entity's functional currency, consolidated in the
group's presentation currency (multi-currency decision 1, 2026-09-26), with group-internal exposures eliminated.

Every stored amount keeps what was sent (money_source: amount, currency, book date, rate). For one filing:

    as sent (currency X, book date d) ─► the holding entity's functional currency F   at the rate on d (step 1)
                                       ─► the filing's presentation currency P       at the filing date T (step 2)

  * step 1 is the entity's own bookkeeping (IAS 21.23): a balance at the closing rate on its book date, a flow at the
    average of the 12 months to it — the same policy intake used. An amount already in F is taken exactly as sent.
  * step 2 is translation (IAS 21.39): balances at the CLOSING rate on the filing's period end, flows (income, rent,
    spend) at the AVERAGE rate of the filing period — or at closing where the organisation's governed `fx_flow_rate`
    says so. Using the average for flows while balances use closing creates a translation difference (IAS 21.41(a));
    it is shown per entity, never buried.
  * An amount stored before currencies were recorded has no money_source: it was entered in EUR, and is treated so.
  * Stored figures whose record does not add up to them (edited by another path) are treated as EUR and COUNTED, so the
    reader sees how much of the book rests on that assumption.
  * A rate the filing cannot get (no source for the currency) refuses the freeze; an organisation's own rate beyond
    its tolerance refuses it too (there is no second-person step on a freeze). Stale rates are frozen, flagged.

Elimination (IFRS 10.B86(c), IFRS 11.B34): an asset / exposure a group company holds against ANOTHER group company
(portfolio_entities.intragroup_entity_id) stays in the holder's solo filing, and is removed from a consolidated
filing that contains both — in full against a fully consolidated counterparty, to the group's share against a
proportionally consolidated one, and not at all against an equity-method one (its balances are not in the group's
figures). Every elimination is listed.

Every rate used is recorded on the frozen filing (`rates_used`), so a later revision of any of them can be found
(fx.rate_changes_since) and the filing flagged for restatement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from services.reference.fx import FxError

# Every money column the engine reads per asset: (flow?, own stake?, the intake fields it is recorded under).
# "own stake" = the group's own figure (scaled by ownership and eliminated); the others describe the COUNTERPARTY
# (its enterprise value, its revenue) and are never scaled by our stake — only translated.
MONEY_COLUMNS: dict[str, tuple[bool, bool, tuple[str, ...]]] = {
    "primary_value_eur": (False, True, ("appraised_value_eur", "property_value_eur", "position_value_eur", "sum_insured_eur")),
    "outstanding_loan_balance_eur": (False, True, ("outstanding_loan_balance_eur",)),
    "insurance_coverage_eur": (False, True, ("insurance_coverage_eur",)),
    "building_value_eur": (False, True, ("building_value_eur",)),
    "contents_value_eur": (False, True, ("contents_value_eur",)),
    "business_interruption_value_eur": (False, True, ("business_interruption_value_eur",)),
    "motor_sum_insured_eur": (False, True, ("motor_sum_insured_eur",)),
    "annual_noi_eur": (True, True, ("annual_noi_eur",)),
    "annual_gross_rental_revenue_eur": (True, True, ("annual_gross_rental_revenue_eur",)),
    "counterparty_evic_eur": (False, False, ("counterparty_evic_eur",)),
    "annual_revenue_eur": (True, False, ("annual_revenue_eur",)),
}
_TIV = ("building_value_eur", "contents_value_eur", "business_interruption_value_eur")   # a sum insured sent in parts
OWN_STAKE = tuple(c for c, (_, own, _) in MONEY_COLUMNS.items() if own)
_TIE = 0.005                                  # a record explains a stored figure within 0.5%
FILING_PERIOD_DAYS = 365


class TranslationError(ValueError):
    pass


@dataclass
class Translation:
    """How one filing presents money. Built by plan(); applied per asset row by the engine (portfolio_engine)."""
    org_id: str
    presentation: str
    period_end: date
    functional: dict[Optional[str], str]                 # reporting entity → functional currency (None = unassigned)
    flow_policy: str = "period_average"
    tolerance_pct: float = 1.0
    scope: Optional[set] = None                          # entities in this filing (None = the whole organisation)
    methods: dict = field(default_factory=dict)          # entity → consolidation method
    weights: dict = field(default_factory=dict)          # entity → ownership weight (root 1.0)
    rates_used: dict = field(default_factory=dict)
    per_entity: dict = field(default_factory=dict)
    eliminations: list = field(default_factory=list)
    unexplained: dict = field(default_factory=lambda: {"n": 0, "value": 0.0})

    @property
    def period_start(self) -> date:
        return self.period_end - timedelta(days=FILING_PERIOD_DAYS - 1)

    def identity(self) -> bool:
        """EUR everywhere — the stored figures are already the answer (nothing to translate, only eliminations)."""
        return self.presentation == "EUR" and all(c == "EUR" for c in self.functional.values())


def presentation_currency(session: Session, org_id: str, entity_id: Optional[str]) -> str:
    """Whole organisation, or a group at the top of the tree → the organisation's presentation currency; a sub-group or
    a single entity → its own (functional) currency, inherited up the tree when not set."""
    from services.governance.entities import effective_currencies, get_entity
    from services.governance.reporting_settings import get_settings
    if entity_id is None:
        return get_settings(session, org_id)["presentation_currency"]
    ent = get_entity(session, org_id, entity_id)
    if ent and ent["has_children"] and not ent["parent_entity_id"]:
        return get_settings(session, org_id)["presentation_currency"]
    return effective_currencies(session, org_id).get(entity_id, {}).get("currency") or \
        get_settings(session, org_id)["presentation_currency"]


def plan(session: Session, org_id: str, entity_id: Optional[str], period_end: date,
         scope: Optional[list] = None, weights: Optional[dict] = None) -> Translation:
    from services.governance.entities import effective_currencies, entity_tree
    from services.intake.money import rate_policy
    pres = presentation_currency(session, org_id, entity_id)
    eff = effective_currencies(session, org_id)
    functional: dict[Optional[str], str] = {k: v["currency"] for k, v in eff.items()}
    functional[None] = pres                               # an unassigned asset is the filer's own
    pol = rate_policy(session, org_id)
    return Translation(org_id=org_id, presentation=pres, period_end=period_end, functional=functional,
                       flow_policy=pol["flow"], tolerance_pct=pol["client_tolerance_pct"],
                       scope=set(scope) if scope else None,
                       methods={e["entity_id"]: e["consolidation_method"] for e in entity_tree(session, org_id)},
                       weights=dict(weights or {}))


# ───────────────────────────── rates ─────────────────────────────

def _rate(session: Session, t: Translation, ccy: str, *, average: bool, start: Optional[date], end: date) -> float:
    """Units of `ccy` per EUR, by the organisation's own chooser (official source, else its own rate compared with it).
    Recorded once per (currency, basis, period)."""
    if ccy == "EUR":
        return 1.0
    key = f"{ccy}|{'average' if average else 'closing'}|{start.isoformat() if start else ''}|{end.isoformat()}"
    hit = t.rates_used.get(key)
    if hit is not None:
        return hit["units_per_eur"]
    from services.intake.money import _choose
    try:
        r = _choose(session, t.org_id, ccy, end, average, (start, end) if average else None)
    except FxError as e:
        raise TranslationError(f"No exchange rate for {ccy} on {end.isoformat()} — the filing can't present it ({e}).") from e
    if r.get("outside_tolerance"):
        raise TranslationError(f"Your own {ccy} rate for {end.isoformat()} is beyond your tolerance: {r.get('note')}. "
                               "Correct it (Admin → Your exchange rates) before freezing.")
    t.rates_used[key] = {"currency": ccy, "basis": "average" if average else "closing",
                         "period_start": start.isoformat() if start else None, "rate_date": r.get("rate_date") or end.isoformat(),
                         "as_of": end.isoformat(), "units_per_eur": float(r["units_per_eur"]), "source": r.get("source"),
                         "stale": bool(r.get("stale")), "note": r.get("note")}
    return float(r["units_per_eur"])


def _step2(session: Session, t: Translation, f: str, flow: bool) -> float:
    """Presentation units per functional unit at the filing date: closing for balances, the period average for flows
    (unless the organisation's policy converts flows at closing too)."""
    if f == t.presentation:
        return 1.0
    avg = flow and t.flow_policy == "period_average"
    start = t.period_start if avg else None
    return _rate(session, t, t.presentation, average=avg, start=start, end=t.period_end) / \
        _rate(session, t, f, average=avg, start=start, end=t.period_end)


def _in_functional(session: Session, t: Translation, entry: dict, f: str) -> float:
    """One recorded amount in the entity's functional currency, at the rate of its own book date (step 1)."""
    if (entry.get("currency") or "EUR") == f:
        return float(entry["amount"])
    eur = float(entry["eur"])
    if f == "EUR":
        return eur
    d = date.fromisoformat(str(entry.get("book_date") or entry.get("period_end"))[:10])
    if entry.get("policy") == "average":
        start = date.fromisoformat(str(entry["period_start"])[:10]) if entry.get("period_start") else d - timedelta(days=364)
        return eur * _rate(session, t, f, average=True, start=start, end=d)
    return eur * _rate(session, t, f, average=False, start=None, end=d)


def from_eur(session: Session, t: Translation, amount: float) -> float:
    """A figure held in EUR (an attested treaty amount, an engine amount), in the presentation currency at closing."""
    return amount * _rate(session, t, t.presentation, average=False, start=None, end=t.period_end)


# ───────────────────────────── per asset ─────────────────────────────

def translate_row(session: Session, t: Translation, row: dict, money_source: Optional[dict]) -> None:
    """Rewrite the row's money columns into the presentation currency (in place) and account for them per entity.
    Keys keep their `_eur` names (the engine's contract); the snapshot says which currency they hold."""
    rid = row.get("reporting_entity_id")
    f = t.functional.get(rid) or t.presentation
    fields = (money_source or {}).get("fields") or {}
    acc = t.per_entity.setdefault(rid, {"functional": f, "n_assets": 0, "balances_functional": 0.0, "balances": 0.0,
                                        "flows_functional": 0.0, "flows": 0.0, "flows_at_closing": 0.0})
    acc["n_assets"] += 1
    for col, (flow, own, sources) in MONEY_COLUMNS.items():
        stored = row.get(col)
        if stored is None:
            continue
        stored = float(stored)
        entries, explained = [], False
        for group in [(s,) for s in sources] + ([_TIV] if col == "primary_value_eur" else []):
            got = [fields[s] for s in group if s in fields and fields[s].get("eur") is not None]
            if not got:
                continue
            entries = entries or got
            if abs(sum(float(e["eur"]) for e in got) - stored) <= _TIE * max(abs(stored), 1.0):
                entries, explained = got, True
                break
        if explained:
            in_f = sum(_in_functional(session, t, e, f) for e in entries)
        else:
            if entries:                                   # recorded, but no longer what is stored: taken as EUR, counted
                t.unexplained["n"] += 1
                t.unexplained["value"] += stored
            in_f = stored if f == "EUR" else stored * _rate(session, t, f, average=False, start=None, end=t.period_end)
        out = in_f * _step2(session, t, f, flow)
        row[col] = out
        if col == "primary_value_eur":
            acc["balances_functional"] += in_f
            acc["balances"] += out
        elif flow and own:
            acc["flows_functional"] += in_f
            acc["flows"] += out
            acc["flows_at_closing"] += in_f * (1.0 if f == t.presentation else
                                              _rate(session, t, t.presentation, average=False, start=None, end=t.period_end)
                                              / _rate(session, t, f, average=False, start=None, end=t.period_end))


def elimination_share(t: Translation, row: dict) -> float:
    """How much of this asset a consolidated filing removes as group-internal (0 = none, 1 = all)."""
    other = row.get("intragroup_entity_id")
    if not other or (t.scope is not None and other not in t.scope):
        return 0.0
    if t.scope is None and other not in t.methods:
        return 0.0
    method = t.methods.get(other, "full")
    if method == "equity":
        return 0.0
    return float(t.weights.get(other, 1.0)) if method == "proportional" else 1.0


def record_elimination(t: Translation, row: dict, share: float, value_before: Optional[float]) -> None:
    t.eliminations.append({"asset_id": row.get("entity_id"), "asset": row.get("entity_name"),
                           "held_by": row.get("reporting_entity_id"), "counterparty": row.get("intragroup_entity_id"),
                           "share_eliminated": round(share, 4),
                           "value_eliminated": round((value_before or 0.0) * share, 2)})


# ───────────────────────────── the frozen record ─────────────────────────────

def summary(t: Translation, names: Optional[dict] = None) -> dict:
    """What the filing freezes about its currency: presentation, policy, every rate used, the per-entity translation
    (with the IAS 21.41(a) difference on flows) and every elimination. Hash-verified with the rest of the payload."""
    names = names or {}
    ents = []
    for rid, a in sorted(t.per_entity.items(), key=lambda kv: names.get(kv[0]) or ""):
        diff = a["flows_at_closing"] - a["flows"]
        ents.append({"entity_id": rid, "entity": names.get(rid) or ("unassigned" if rid is None else rid),
                     "functional_currency": a["functional"], "n_assets": a["n_assets"],
                     "balances_functional": round(a["balances_functional"], 2), "balances": round(a["balances"], 2),
                     "flows_functional": round(a["flows_functional"], 2), "flows": round(a["flows"], 2),
                     "translation_difference": round(diff, 2)})
    return {"presentation_currency": t.presentation, "period_end": t.period_end.isoformat(),
            "period_start": t.period_start.isoformat(),
            "basis": {"balances": "closing rate on the period end", "flows": ("period average" if t.flow_policy == "period_average"
                                                                           else "closing rate (organisation policy)"),
                      "own_book": "each amount in its entity's functional currency at the rate on its book date"},
            "rates_used": sorted(t.rates_used.values(), key=lambda r: (r["currency"], r["basis"], r["as_of"])),
            "n_stale_rates": sum(1 for r in t.rates_used.values() if r["stale"]),
            "translation": ents,
            "translation_difference_total": round(sum(e["translation_difference"] for e in ents), 2),
            "eliminations": t.eliminations[:500], "n_eliminations": len(t.eliminations),
            "value_eliminated_total": round(sum(e["value_eliminated"] for e in t.eliminations), 2),
            "unexplained_as_eur": {"n": t.unexplained["n"], "value": round(t.unexplained["value"], 2)}}


def revisions_since(session: Session, org_id: str, fx: Optional[dict], since) -> list[dict]:
    """Rates a frozen filing used that have changed since it was frozen: an official source corrected a day in the
    window the rate stands for (the closing day, or any day of an average's period), or the organisation submitted a
    newer rate of its own for it. Any hit means the filing's money may need restating."""
    from sqlalchemy import text
    out: list[dict] = []
    for r in (fx or {}).get("rates_used") or []:
        end = date.fromisoformat(r["as_of"])
        start = date.fromisoformat(r["period_start"]) if r.get("period_start") else date.fromisoformat(r["rate_date"][:10])
        if r.get("source") == "client":
            n = session.execute(text("""
                SELECT count(*) FROM fx_client_rates WHERE org_id = CAST(:o AS uuid) AND ccy = :c AND submitted_at > :t
                   AND basis = :b AND rate_date BETWEEN :s AND :e
            """), {"o": org_id, "c": r["currency"], "t": since, "b": "period_average" if r["basis"] == "average" else "closing",
                   "s": start, "e": end}).scalar()
            if n:
                out.append({**r, "change": f"{n} newer rate(s) of your own submitted since the freeze"})
            continue
        hits = session.execute(text("""
            SELECT rate_date, source, CAST(units_per_eur AS FLOAT) AS was, CAST(new_units_per_eur AS FLOAT) AS now, change
            FROM fx_rate_history WHERE ccy = :c AND replaced_at > :t AND rate_date BETWEEN :s AND :e
            ORDER BY replaced_at DESC
        """), {"c": r["currency"], "t": since, "s": start, "e": end}).mappings().all()
        if hits:
            h = hits[0]
            out.append({**r, "change": f"{len(hits)} rate(s) revised by the source since the freeze (e.g. {h['source']} "
                                       f"{h['rate_date'].isoformat()}: {h['was']:g} → {h['now'] if h['now'] is not None else 'withdrawn'})"})
    return out
