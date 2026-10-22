"""Tested losses into decisions (the product owner's decisions of 2026-10-22). The loss engine's tested figures become
a risk indicator — the book's tested yearly loss — and a decision signal: the assets whose tested yearly loss is at or
above the share of their value the institution states (method.loss_signal_share; no default — not stated, no signal,
a named gap). Figures are read only through the one door (services.loss.figures.tested): a held or untested figure
is never carried. Everything is today's climate (baseline, current).

  book_of(session, org_id)        the book of physical assets the organisation's type holds
  lead(figure, headline)          the figure that leads: a storm figure's expected yearly loss; for flood, the figure
                                  the institution states leads (calc setting loss_flood_headline) — defended, or
                                  undefended; where the protection map holds no level, the undefended figure, marked
                                  'protection unknown' (the decisions of 2026-10-16). None for flood while not stated.
  carried(session, org_id)        the book's tested figures, each with its leading loss and that loss's share of the
                                  value its curve applies to; what was withheld, counted by why
  yearly_loss(session, org_id)    the indicator: the sum of the leading losses, € per year — None (with the reason)
                                  when there is no run, no tested figure, or flood figures wait for the stated lead
  signals(session, org_id, m)     the assets with a figure at or above the stated share, largest loss first; `why`
                                  names what holds the list back (as for the indicator)
  asset_share(session, org_id, e) one asset's largest share today — what a loss watch is re-checked on
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.loss import figures as door

BOOK = {"bank": "banking", "insurer": "insurance", "reit": "realestate", "asset_manager": "assetmgmt",
        "manufacturer": "company_sites"}
TODAY = ("baseline", "current")
FLOOD_LEAD_NOT_STATED = "flood_lead_not_stated"      # a withheld count: tested flood figures waiting for the stated lead


def book_of(session: Session, org_id: str) -> Optional[str]:
    kind = session.execute(text("SELECT type FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": org_id}).scalar()
    return BOOK.get(kind)


def lead(f: dict, headline: Optional[str]) -> Optional[dict]:
    if f["peril"] != "flood":
        return {"basis": None, "eur": f["eal_eur"], "low": f["eal_low_eur"], "high": f["eal_high_eur"]}
    if headline is None:
        return None
    if headline == "defended" and f["eal_defended_eur"] is not None:
        return {"basis": "defended", "eur": f["eal_defended_eur"], "low": f["eal_defended_low_eur"],
                "high": f["eal_defended_high_eur"]}
    return {"basis": "undefended" if headline == "undefended" else "protection_unknown", "eur": f["eal_eur"],
            "low": f["eal_low_eur"], "high": f["eal_high_eur"]}


def _share(eur: Optional[float], value: float) -> Optional[float]:
    return None if eur is None else eur / value


def carried(session: Session, org_id: str) -> dict:
    from services.calc_settings import get_calc_settings
    book = book_of(session, org_id)
    out = {"book": book, "run_id": None, "as_of": None, "headline": None, "figures": [], "withheld": {}, "gaps": {},
           "missing": None}
    if book is None:
        return {**out, "missing": "loss.signal.no_book"}
    run = door.tested(session, org_id, book, *TODAY)
    if run is None:
        return {**out, "missing": "loss.signal.no_run"}
    headline = get_calc_settings(session, org_id).get("loss_flood_headline")
    withheld = dict(run["withheld"])
    rows = []
    for f in run["figures"]:
        lf = lead(f, headline)
        if lf is None:
            withheld[FLOOD_LEAD_NOT_STATED] = withheld.get(FLOOD_LEAD_NOT_STATED, 0) + 1
            continue
        v = f["exposed_value_eur"]                    # a tested figure always has the value its curve applies to
        rows.append({"asset_id": f["asset_id"], "peril": f["peril"], "curve_key": f["curve_key"],
                     "exposed_value_eur": v, "basis": lf["basis"], "loss_eur": lf["eur"],
                     "loss_low_eur": lf["low"], "loss_high_eur": lf["high"], "share": _share(lf["eur"], v),
                     "share_low": _share(lf["low"], v), "share_high": _share(lf["high"], v)})
    return {**out, "run_id": run["run_id"], "as_of": run["as_of"], "headline": headline, "figures": rows,
            "withheld": withheld, "gaps": run["gaps"]}


def missing(c: dict) -> Optional[str]:
    """Why the book's tested yearly loss is not a figure: no book or run, flood figures waiting for the stated lead
    (a sum without them would understate the book), or no tested figure at all."""
    if c["missing"]:
        return c["missing"]
    if c["withheld"].get(FLOOD_LEAD_NOT_STATED):
        return "loss.signal.flood_lead_not_stated"
    if not c["figures"]:
        return "loss.signal.no_tested_figure"
    return None


def yearly_loss(session: Session, org_id: str) -> dict:
    c = carried(session, org_id)
    why = missing(c)
    return {**c, "value": None if why else sum(f["loss_eur"] for f in c["figures"]), "why": why}


def signals(session: Session, org_id: str, method) -> dict:
    level = method.get("method.loss_signal_share")
    c = carried(session, org_id)
    res = {**{k: c[k] for k in ("book", "run_id", "as_of", "headline", "withheld", "gaps")}, "why": missing(c),
           "level": level, "gap": method.gap_text(), "carried": len(c["figures"]), "signals": []}
    if level is None:
        return res
    hits: dict[str, list[dict]] = {}
    for f in c["figures"]:
        if f["share"] >= level:
            hits.setdefault(f["asset_id"], []).append(f)
    if not hits:
        return res
    names = {r["eid"]: r for r in session.execute(text("""
        SELECT entity_id::text AS eid, entity_name, country, region, CAST(primary_value_eur AS FLOAT) AS value_eur
        FROM portfolio_entities WHERE org_id = CAST(:o AS uuid) AND entity_id = ANY(CAST(:ids AS uuid[]))"""),
        {"o": org_id, "ids": list(hits)}).mappings()}
    out = []
    for eid, fs in hits.items():
        e = names.get(eid) or {}
        out.append({"entity_id": eid, "entity_name": e.get("entity_name"), "country": e.get("country"),
                    "region": e.get("region"), "value_eur": e.get("value_eur"),
                    "loss_eur": sum(f["loss_eur"] for f in fs), "share": max(f["share"] for f in fs),
                    "figures": sorted(fs, key=lambda f: -f["loss_eur"])})
    out.sort(key=lambda s: (-s["loss_eur"], -s["share"], s["entity_id"]))
    return {**res, "signals": out}


def asset_share(session: Session, org_id: str, entity_id: str, c: Optional[dict] = None) -> Optional[float]:
    """The asset's largest tested-loss share today — None when it has no carried figure. `c`: the book's carried
    figures, when the caller has already read them."""
    c = c if c is not None else carried(session, org_id)
    shares = [f["share"] for f in c["figures"] if f["asset_id"] == entity_id]
    return max(shares) if shares else None
