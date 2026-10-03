"""The banking book's counterparties for the governed intake (template bank_counterparties; E119).

One row per counterparty, identified exactly as the loan tape identifies it (portfolio_entities.borrower_entity_id: its
LEI or the bank's own stable id). What the bank states about the counterparty is stated ONCE here, not per exposure:

  total liabilities   its accounting liabilities and shareholders' equity, from its balance sheet, with the balance
                      sheet's date (the row's book date; the amount converts at that day's closing rate) — the
                      denominator Annex XL, Template 1, column i names: 'their exposures ... towards the counterparty
                      compared to the total liabilities (accounting liabilities and shareholders' equity) of the
                      counterparty'
  revenue             its revenue for the financial year ending on the row's book date (a flow: the average rate of the
                      year) — what a sector-average scope 3 intensity per EUR million of revenue multiplies (E133)
  issuer              the shared issuer reference entry whose LEI the id is (an exact LEI match, never a name match)

Stating the figure clears a conflict the migration recorded where the counterparty's exposures disagreed
(p3_t1_counterparty_20261002). A row is refused with a message the bank can act on; nothing is guessed.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.ingest.sector_contract import RowIssue, Sector, _m, _s

REF_MAX = 20                         # portfolio_entities.borrower_entity_id is VARCHAR(20): the id the loan tape can hold
_ISSUER = "(SELECT i.issuer_id FROM issuers i WHERE i.lei = CAST(:external_ref AS VARCHAR(20)))"


def _prepare(session: Session, org_id: str) -> dict:
    return {}


def _build(ctx: dict, row: dict) -> dict:
    ref = _s(row, "counterparty_ref")
    if not ref:
        raise RowIssue("the counterparty id is required — as your loan tape gives it (Counterparty ID (LEI))")
    if len(ref) > REF_MAX:
        raise RowIssue(f"counterparty id '{ref}' is longer than {REF_MAX} characters — the loan tape cannot hold it")
    tl, rev = _m(row, "total_liabilities_eur"), _m(row, "counterparty_revenue_eur")
    d = None
    if tl is not None and tl <= 0:
        raise RowIssue("total liabilities and equity must be greater than zero")
    if rev is not None and rev <= 0:
        raise RowIssue("revenue must be greater than zero")
    if tl is not None or rev is not None:
        raw = _s(row, "book_date")
        if raw is None:
            raise RowIssue("say the end of the financial year the figures are taken from (book_date)")
        try:
            d = date.fromisoformat(raw[:10]).isoformat()
        except ValueError:
            raise RowIssue(f"financial year end '{raw}' is not a date (YYYY-MM-DD)")
    return {"external_ref": ref, "counterparty_name": _s(row, "counterparty_name"), "total_liabilities_eur": tl,
            "total_liabilities_date": d if tl is not None else None, "counterparty_revenue_eur": rev,
            "revenue_period_end": d if rev is not None else None, "latitude": None, "longitude": None}


def _existing(session: Session, org_id: str) -> list[dict]:
    return [dict(r) for r in session.execute(text("""
        SELECT counterparty_id::text AS entity_id, counterparty_ref AS external_ref, counterparty_name,
               CAST(total_liabilities_eur AS FLOAT) AS total_liabilities_eur,
               to_char(total_liabilities_date, 'YYYY-MM-DD') AS total_liabilities_date,
               CAST(revenue_eur AS FLOAT) AS counterparty_revenue_eur,
               to_char(revenue_period_end, 'YYYY-MM-DD') AS revenue_period_end,
               NULL::float AS latitude, NULL::float AS longitude
        FROM bank_counterparties WHERE org_id = CAST(:o AS uuid)"""), {"o": org_id}).mappings().all()]


def _insert(session: Session, org_id: str, ctx: dict, recs: list[dict]) -> None:
    for r in recs:
        r.setdefault("entity_id", str(uuid.uuid4()))
        r["org_id"] = org_id
    session.execute(text(f"""
        INSERT INTO bank_counterparties (counterparty_id, org_id, counterparty_ref, counterparty_name, issuer_id,
                                         total_liabilities_eur, total_liabilities_date, revenue_eur, revenue_period_end)
        VALUES (CAST(:entity_id AS uuid), CAST(:org_id AS uuid), CAST(:external_ref AS VARCHAR(20)), :counterparty_name, {_ISSUER},
                CAST(:total_liabilities_eur AS NUMERIC), CAST(:total_liabilities_date AS date),
                CAST(:counterparty_revenue_eur AS NUMERIC), CAST(:revenue_period_end AS date))"""), recs)


def _update(session: Session, org_id: str, ctx: dict, recs: list[dict]) -> None:
    for r in recs:
        r["org_id"] = org_id
    # the one figure the bank states replaces a conflict the per-exposure figures left (it is now resolved by statement)
    session.execute(text(f"""
        UPDATE bank_counterparties SET counterparty_name = :counterparty_name,
               issuer_id = COALESCE({_ISSUER}, issuer_id),
               total_liabilities_eur = CAST(:total_liabilities_eur AS NUMERIC),
               total_liabilities_date = CAST(:total_liabilities_date AS date),
               revenue_eur = CAST(:counterparty_revenue_eur AS NUMERIC),
               revenue_period_end = CAST(:revenue_period_end AS date),
               liabilities_conflict = CASE WHEN CAST(:total_liabilities_eur AS NUMERIC) IS NULL THEN liabilities_conflict END,
               updated_at = now()
        WHERE counterparty_id = CAST(:entity_id AS uuid) AND org_id = CAST(:org_id AS uuid)"""), recs)


COUNTERPARTIES = Sector("bank_counterparties", "counterparty_name", "total_liabilities_eur",
                        ("counterparty_name", "total_liabilities_eur", "total_liabilities_date", "counterparty_revenue_eur",
                         "revenue_period_end"),
                        _prepare, _build, _existing, _insert, _update,
                        table="bank_counterparties", id_column="counterparty_id", asset_book=False)


# ── reading ──

def listing(session: Session, org_id: str) -> dict:
    """Every counterparty the banking book names (its exposures' ids) and every one the bank has stated, with what is
    stated, how many exposures link to it, and whether a conflict blocks its figure."""
    rows = session.execute(text("""
        WITH refs AS (
            SELECT e.borrower_entity_id AS ref, count(*) AS n_exposures,
                   CAST(sum(x.outstanding_loan_balance_eur) AS FLOAT) AS gross_eur
            FROM portfolio_entities e JOIN ext_banking x ON x.entity_id = e.entity_id
            WHERE e.org_id = CAST(:o AS uuid) AND e.vertical = 'banking' AND e.source = 'own'
              AND e.borrower_entity_id IS NOT NULL
            GROUP BY 1)
        SELECT COALESCE(c.counterparty_ref, r.ref) AS counterparty_ref, c.counterparty_name,
               CAST(c.total_liabilities_eur AS FLOAT) AS total_liabilities_eur, c.total_liabilities_date,
               CAST(c.revenue_eur AS FLOAT) AS revenue_eur, c.revenue_period_end,
               c.liabilities_conflict, c.issuer_id::text AS issuer_id, i.name AS issuer_name, c.money_source,
               COALESCE(r.n_exposures, 0) AS n_exposures, r.gross_eur, c.updated_at
        FROM refs r FULL JOIN (SELECT * FROM bank_counterparties WHERE org_id = CAST(:o AS uuid)) c ON c.counterparty_ref = r.ref
        LEFT JOIN issuers i ON i.issuer_id = c.issuer_id
        ORDER BY r.gross_eur DESC NULLS LAST, 1"""), {"o": org_id}).mappings().all()
    n_none = session.execute(text("""
        SELECT count(*) FROM portfolio_entities e JOIN ext_banking x ON x.entity_id = e.entity_id
        WHERE e.org_id = CAST(:o AS uuid) AND e.vertical = 'banking' AND e.source = 'own' AND e.borrower_entity_id IS NULL
    """), {"o": org_id}).scalar()
    return {"counterparties": [{**dict(r), "total_liabilities_date": r["total_liabilities_date"].isoformat()
                                if r["total_liabilities_date"] else None,
                                "revenue_period_end": r["revenue_period_end"].isoformat() if r["revenue_period_end"] else None,
                                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None}
                               for r in rows],
            "n_exposures_without_counterparty": int(n_none or 0)}
