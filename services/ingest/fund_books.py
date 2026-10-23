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

  issuer_figures   one row per company and financial year: what the manager states about a company it holds (revenue,
                   EVIC, physical asset value, emissions, the adverse-impact facts, Taxonomy shares), dated by the
                   financial year end — written by the one write the API uses (services/funds/holding.apply_enrichment)
                   with the same rules (services/funds/holding.IssuerFigures). Voluntary adverse-impact values, keyed by
                   indicator, still come by the API only.
"""
from __future__ import annotations

import re
import uuid
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.ingest.fields import norm_token
from services.ingest.sector_contract import RowIssue, Sector, _bool, _m, _s, _vocab

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
    if fund_id is None and norm_token(fund or "") in ctx.get("in_file", {}).get("funds", ()):
        fund_id = f"in-file:{norm_token(fund)}"      # a check of the whole file: its Funds sheet lands first (E323)
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


# ── issuer figures ───────────────────────────────────────────────────────────────────────────────────────────────

ISSUER_FIGURES_FIELDS = ("revenue_eur", "evic_eur", "physical_asset_value_eur", "scope1_tco2e", "scope2_tco2e",
                         "scope3_tco2e", "nace_code", "energy_consumption_gwh", "non_renewable_consumption_pct",
                         "non_renewable_production_pct", "biodiversity_sensitive_ops", "emissions_to_water_tonnes",
                         "hazardous_waste_tonnes", "ungc_oecd_violation", "ungc_oecd_no_monitoring", "gender_pay_gap_pct",
                         "board_female_pct", "controversial_weapons", "taxonomy_eligible_pct", "taxonomy_aligned_pct",
                         "taxonomy_aligned_capex_pct", "taxonomy_fossil_gas_aligned_pct", "taxonomy_nuclear_aligned_pct",
                         "taxonomy_fossil_gas_aligned_capex_pct", "taxonomy_nuclear_aligned_capex_pct",
                         "taxonomy_dnsh_ok", "taxonomy_min_safeguards_ok")
_MONEY = ("revenue_eur", "evic_eur", "physical_asset_value_eur")
_FLAGS = ("biodiversity_sensitive_ops", "ungc_oecd_violation", "ungc_oecd_no_monitoring", "controversial_weapons",
          "taxonomy_dnsh_ok", "taxonomy_min_safeguards_ok")


def _figures_prepare(session: Session, org_id: str) -> dict:
    return {"org_id": org_id}


def _figures_build(ctx: dict, row: dict) -> dict:
    from core.errors import UserError
    from services.funds.holding import IssuerFigures
    isin = (_s(row, "isin") or "").upper().replace(" ", "")
    if not isin_ok(isin):
        raise RowIssue(f"'{isin}' is not a valid ISIN (12 characters with a correct check digit)")
    try:
        year_end = date.fromisoformat((_s(row, "book_date") or "")[:10])
    except ValueError:
        raise RowIssue("the financial year end is required (YYYY-MM-DD)")
    rec = {k: (_bool(row, k) if k in _FLAGS else _s(row, k) if k == "nace_code" else _m(row, k, 6))
           for k in ISSUER_FIGURES_FIELDS}
    if all(v is None for v in rec.values()):
        raise RowIssue("the row states no figure about the company")
    try:            # the same rules as figures sent with a holding by the API (taxonomy parts within the aligned share …)
        IssuerFigures(isin=isin, reporting_year=year_end.year, **{k: v for k, v in rec.items() if v is not None})
    except UserError as e:
        said = e.body()["error"]
        raise RowIssue(said["detail"].get("what") or said["message"]) from e
    return {**rec, "external_ref": f"{isin}|{year_end.year}", "isin": isin, "financial_year_end": year_end.isoformat(),
            "reporting_year": year_end.year, "latitude": None, "longitude": None}


def _figures_existing(session: Session, org_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT e.emission_id::text AS entity_id, s.isin, e.reporting_year, CAST(e.revenue_eur AS FLOAT) AS revenue_eur,
               CAST(e.evic_eur AS FLOAT) AS evic_eur, CAST(e.physical_asset_value_eur AS FLOAT) AS physical_asset_value_eur,
               CAST(e.scope1_tco2e AS FLOAT) AS scope1_tco2e, CAST(e.scope2_tco2e AS FLOAT) AS scope2_tco2e,
               CAST(e.scope3_tco2e AS FLOAT) AS scope3_tco2e
        FROM issuer_emissions e JOIN securities s ON s.issuer_id = e.issuer_id
        WHERE e.org_id = CAST(:o AS uuid) AND e.source = 'client'"""), {"o": org_id}).mappings().all()
    return [{**dict(r), "external_ref": f"{r['isin']}|{r['reporting_year']}", "latitude": None, "longitude": None}
            for r in rows]


def _figures_write(session: Session, org_id: str, ctx: dict, recs: list[dict]) -> None:
    """Each company's figures for each year through the one write the API uses (services/funds/holding.apply_enrichment):
    an amount sent in another currency converts there at the year's rates, as it does from the API."""
    from services.funds.holding import IssuerFigures, apply_enrichment
    from services.reference.resolver import resolve_isin
    for r in recs:
        res = resolve_isin(session, r["isin"], org_id=org_id)
        if res.status not in ("resolved", "cached") or not res.issuer_id:
            ctx.setdefault("onboarding", []).append({"coverage": {"unmatched": [r["isin"]]}})
            r["entity_id"] = str(uuid.uuid4())                       # an unresolved ISIN states nothing
            continue
        sent = r.get("_money") or {}
        fig = {k: r[k] for k in ISSUER_FIGURES_FIELDS if r.get(k) is not None and k not in _MONEY}
        ccys = {e["currency"] for e in sent.values()}
        for k in _MONEY:
            if k not in sent:
                continue
            if sent[k]["currency"] == "EUR" or len(ccys) > 1:
                fig[k] = r[k]                                        # in EUR, as the intake converted it
            else:
                fig[k.removesuffix("_eur")] = sent[k]["amount"]      # as sent, converted by the one write
        if len(ccys) == 1 and next(iter(ccys)) != "EUR" and any(k in sent for k in _MONEY):
            fig["financials_currency"] = next(iter(ccys))
        apply_enrichment(session, res.issuer_id, org_id,
                         IssuerFigures(isin=r["isin"], reporting_year=r["reporting_year"],
                                       financials_date=date.fromisoformat(r["financial_year_end"]), **fig))
        r["entity_id"] = session.execute(text("""
            SELECT emission_id::text FROM issuer_emissions WHERE issuer_id = :i AND org_id = CAST(:o AS uuid)
              AND reporting_year = :y AND source = 'client'"""),
            {"i": res.issuer_id, "o": org_id, "y": r["reporting_year"]}).scalar() or str(uuid.uuid4())


ISSUER_FIGURES = Sector("issuer_figures", "isin", "_no_value", ISSUER_FIGURES_FIELDS[:6],
                        _figures_prepare, _figures_build, _figures_existing, _figures_write, _figures_write,
                        table="issuer_emissions", id_column="emission_id", asset_book=False, money_record=True)

SECTORS = (FUNDS, FUND_HOLDINGS, ISSUER_FIGURES)
