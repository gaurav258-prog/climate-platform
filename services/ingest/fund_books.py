"""An asset manager's funds and their holdings by ISIN, received through the governed intake — the books of its standard
file that an Art-8/9 manager's reporting starts from (the product owner's decision of 2026-10-23: one standard file per
sector, every book through the same checks, second-person approval and landing).

  funds            one row per fund as the manager states it — name, type, SFDR article, base currency, parent, LEI —
                   checked and written by the one fund registry (services/funds/registry.py), as POST /v1/funds does
  fund_holdings    one row per position: the fund (by its name), the ISIN, the market value on the row's as-of date (the
                   intake converts it to EUR at that day's closing rate and keeps the amount as sent), the asset class.
                   Landing onboards each fund's positions through the one onboarding (services/funds/onboarding.py), as
                   POST /v1/funds/{id}/holdings does: each ISIN resolved, its issuer located, the position value-weighted.
                   An ISIN the register cannot resolve is reported by the landing check, never positioned.

The issuer data a manager holds (revenue, EVIC, emissions …) has its own financial-year date and currency, so it is not
read from a holding row here; it is sent with the holdings by the API (and is the next book of the standard file).
"""
from __future__ import annotations

import re
import uuid
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.ingest.fields import norm_token
from services.ingest.sector_contract import RowIssue, Sector, _m, _s, _vocab

ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def isin_ok(isin: str) -> bool:
    """ISO 6166: two letters, nine characters, one check digit (Luhn over the letters expanded to numbers)."""
    if not ISIN.match(isin):
        return False
    digits = "".join(str(int(c, 36)) for c in isin[:-1])
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            d = d - 9 if d > 9 else d
        total += d
    return (10 - total % 10) % 10 == int(isin[-1])


# ── funds ────────────────────────────────────────────────────────────────────────────────────────────────────────

def _funds_prepare(session: Session, org_id: str) -> dict:
    rows = session.execute(text("SELECT fund_id::text, name FROM funds WHERE org_id = CAST(:o AS uuid)"), {"o": org_id}).all()
    return {"funds": {norm_token(n): f for f, n in rows}, "org_id": org_id}


def _funds_build(ctx: dict, row: dict) -> dict:
    name = _s(row, "fund_name")
    if not name:
        raise RowIssue("the fund's name is required")
    parent = _s(row, "parent_fund")
    return {"external_ref": norm_token(name), "fund_name": name, "fund_type": _vocab(row, "fund_type", "fund_type"),
            "sfdr_classification": _vocab(row, "sfdr_classification", "sfdr_article"),
            "base_currency": (_s(row, "base_currency") or "").upper() or None, "parent_fund": parent,
            "fund_lei": (_s(row, "fund_lei") or "").upper() or None, "latitude": None, "longitude": None}


def _funds_existing(session: Session, org_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT f.fund_id::text AS entity_id, f.name AS fund_name, f.fund_type, f.sfdr_classification, f.base_currency,
               p.name AS parent_fund, f.lei AS fund_lei
        FROM funds f LEFT JOIN funds p ON p.fund_id = f.parent_fund_id WHERE f.org_id = CAST(:o AS uuid)"""),
        {"o": org_id}).mappings().all()
    return [{**dict(r), "external_ref": norm_token(r["fund_name"]), "latitude": None, "longitude": None} for r in rows]


def _stated(session: Session, org_id: str, r: dict, existing_id=None) -> dict:
    from services.funds import registry
    parent = None
    if r.get("parent_fund"):
        parent = session.execute(text("SELECT fund_id::text FROM funds WHERE org_id = CAST(:o AS uuid) AND lower(name) = lower(:n)"),
                                 {"o": org_id, "n": r["parent_fund"]}).scalar()
        if parent is None:
            raise RowIssue(f"parent fund '{r['parent_fund']}' is not one of your funds")
    return registry.check(session, org_id, name=r["fund_name"], fund_type=r["fund_type"],
                          sfdr_classification=r["sfdr_classification"], base_currency=r["base_currency"],
                          parent_fund_id=parent, lei=r.get("fund_lei"), existing_id=existing_id)


def _funds_insert(session: Session, org_id: str, ctx: dict, recs: list[dict]) -> None:
    from services.funds import registry
    for r in sorted(recs, key=lambda r: bool(r.get("parent_fund"))):      # a parent before its sub-portfolios
        r["entity_id"] = registry.create(session, org_id, _stated(session, org_id, r), actor_id=ctx.get("actor_id"))


def _funds_update(session: Session, org_id: str, ctx: dict, recs: list[dict]) -> None:
    from services.funds import registry
    for r in recs:
        registry.update(session, org_id, r["entity_id"], _stated(session, org_id, r, r["entity_id"]),
                        actor_id=ctx.get("actor_id"))


FUNDS = Sector("funds", "fund_name", "_no_value",
               ("fund_name", "fund_type", "sfdr_classification", "base_currency", "parent_fund", "fund_lei"),
               _funds_prepare, _funds_build, _funds_existing, _funds_insert, _funds_update,
               table="funds", id_column="fund_id", asset_book=False)


# ── fund holdings ────────────────────────────────────────────────────────────────────────────────────────────────

def _holdings_prepare(session: Session, org_id: str) -> dict:
    return _funds_prepare(session, org_id)


def _holdings_build(ctx: dict, row: dict) -> dict:
    fund = _s(row, "fund_name")
    fund_id = ctx["funds"].get(norm_token(fund or ""))
    if fund_id is None:
        raise RowIssue(f"fund '{fund}' is not one of your funds — add it on the Funds sheet first")
    isin = (_s(row, "isin") or "").upper().replace(" ", "")
    if not isin_ok(isin):
        raise RowIssue(f"'{isin}' is not a valid ISIN (12 characters with a correct check digit)")
    value = _m(row, "market_value_eur")
    if value is None or value <= 0:
        raise RowIssue("the market value must be greater than zero")
    raw = _s(row, "book_date")
    try:
        as_of = date.fromisoformat((raw or "")[:10])
    except ValueError:
        raise RowIssue("the as-of date is required (YYYY-MM-DD)")
    return {"external_ref": f"{fund_id}|{isin}|{as_of.isoformat()}", "fund_id": fund_id, "fund_name": fund, "isin": isin,
            "market_value_eur": value, "asset_class": _vocab(row, "asset_class", "asset_class"), "as_of_date": as_of.isoformat(),
            "latitude": None, "longitude": None}


def _holdings_existing(session: Session, org_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT p.position_id::text AS entity_id, p.fund_id::text AS fund_id, f.name AS fund_name, s.isin,
               CAST(p.market_value_eur AS FLOAT) AS market_value_eur, s.asset_class, p.as_of_date
        FROM fund_positions p JOIN funds f ON f.fund_id = p.fund_id JOIN securities s ON s.security_id = p.security_id
        WHERE f.org_id = CAST(:o AS uuid)"""), {"o": org_id}).mappings().all()
    return [{**dict(r), "as_of_date": r["as_of_date"].isoformat(),
             "external_ref": f"{r['fund_id']}|{r['isin']}|{r['as_of_date'].isoformat()}", "latitude": None,
             "longitude": None} for r in rows]


def _holding(Holding, r: dict):
    """The position as onboarding takes it: its EUR value (converted by the intake at the row's as-of date) and the
    amount and currency as sent (the record's money, kept for this book: Sector.money_record)."""
    sent = (r.get("_money") or {}).get("market_value_eur") or {}
    ccy = (sent.get("currency") or "EUR").upper()
    return Holding(isin=r["isin"], market_value_eur=r["market_value_eur"], asset_class=r.get("asset_class"), currency=ccy,
                   market_value=sent.get("amount") if ccy != "EUR" else None)


def _holdings_write(session: Session, org_id: str, ctx: dict, recs: list[dict]) -> None:
    """Each fund's positions for each as-of date through the one onboarding; each record then carries its position."""
    from services.funds.holding import Holding, HoldingsUpload
    from services.funds.onboarding import onboard
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in recs:
        groups.setdefault((r["fund_id"], r["as_of_date"]), []).append(r)
    reports = ctx.setdefault("onboarding", [])
    for (fund_id, as_of), rs in groups.items():
        body = HoldingsUpload(as_of_date=date.fromisoformat(as_of), holdings=[_holding(Holding, r) for r in rs])
        reports.append({"fund_id": fund_id, "as_of_date": as_of, **onboard(session, org_id, fund_id, body, ctx.get("actor_id"))})
        ids = dict(session.execute(text("""
            SELECT s.isin, p.position_id::text FROM fund_positions p JOIN securities s ON s.security_id = p.security_id
            WHERE p.fund_id = CAST(:f AS uuid) AND p.as_of_date = CAST(:d AS date)"""), {"f": fund_id, "d": as_of}).all())
        for r in rs:
            r["entity_id"] = ids.get(r["isin"]) or str(uuid.uuid4())     # an unresolved ISIN holds no position


FUND_HOLDINGS = Sector("fund_holdings", "isin", "market_value_eur", ("market_value_eur", "asset_class"),
                       _holdings_prepare, _holdings_build, _holdings_existing, _holdings_write, _holdings_write,
                       table="fund_positions", id_column="position_id", asset_book=False, money_record=True)

SECTORS = (FUNDS, FUND_HOLDINGS)
