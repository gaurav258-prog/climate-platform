"""An organisation withdraws the issuer data it stated itself (E146) — figures uploaded in error, or for a company it no
longer reports on. Every org-scoped row about the issuer goes: its emissions (stated, and the estimates the platform
made from what it stated), ESG metrics, Taxonomy KPIs, voluntary PAI values and its plausibility confirmations. The
shared reference (org_id NULL: GLEIF identity, published or vendor figures) is never touched, nor another organisation's
data; a filing already frozen keeps what it printed. Each withdrawn row is kept in the audit record, with the reason.
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

# the organisation-scoped issuer stores this module reads and clears itself; the Taxonomy KPI store is its own owner's
# (services.issuer_taxonomy — one reader and writer, test_one_store_per_fact), reached through it
TABLES = ("issuer_emissions", "issuer_esg_metrics", "issuer_voluntary_pai", "issuer_data_confirmations")
TAXONOMY = "issuer_taxonomy_kpi"
STORES = (*TABLES, TAXONOMY)
MIN_REASON = 10


class WithdrawError(ValueError):
    """The request cannot be done as asked (e.g. no reason)."""


class NothingToWithdraw(WithdrawError):
    """No such issuer, or this organisation holds no data of its own about it."""


def held(session: Session, org_id: str, issuer_id: str) -> dict[str, int]:
    """How many rows of this organisation's own data each store holds about the issuer."""
    from services import issuer_taxonomy
    out = {t: session.execute(text(f"SELECT count(*) FROM {t} WHERE org_id = CAST(:o AS uuid) AND issuer_id = CAST(:i AS uuid)"),
                              {"o": org_id, "i": issuer_id}).scalar() for t in TABLES}
    return {**out, TAXONOMY: len(issuer_taxonomy.org_rows(session, org_id, issuer_id))}


def issuers_with_own_data(session: Session, org_id: str) -> list[dict]:
    """Every issuer the organisation holds data of its own about: [{issuer_id, name, lei}]."""
    from services import issuer_taxonomy
    ids = {r["issuer_id"] for r in issuer_taxonomy.org_rows(session, org_id)}
    for t in TABLES:
        ids |= set(session.execute(text(f"SELECT DISTINCT issuer_id::text FROM {t} WHERE org_id = CAST(:o AS uuid)"),
                                   {"o": org_id}).scalars())
    return [dict(r) for r in session.execute(text("""
        SELECT issuer_id::text AS issuer_id, name, lei FROM issuers WHERE issuer_id = ANY(CAST(:ids AS uuid[])) ORDER BY name"""),
        {"ids": sorted(ids)}).mappings()]


def withdraw(session: Session, org_id: str, issuer_id: str, reason: str, actor_user_id: str | None) -> dict:
    from api.services.rbac import write_audit
    why = (reason or "").strip()
    if len(why) < MIN_REASON:
        raise WithdrawError(f"say why the data is withdrawn (at least {MIN_REASON} characters)")
    name = session.execute(text("SELECT name FROM issuers WHERE issuer_id = CAST(:i AS uuid)"), {"i": issuer_id}).scalar()
    if name is None:
        raise NothingToWithdraw("issuer not found")
    from services import issuer_taxonomy
    gone: dict[str, list] = {}
    tax = issuer_taxonomy.withdraw_org(session, org_id, issuer_id)
    if tax:
        gone[TAXONOMY] = tax
    for t in TABLES:
        rows = session.execute(text(f"""DELETE FROM {t} WHERE org_id = CAST(:o AS uuid) AND issuer_id = CAST(:i AS uuid)
                                        RETURNING to_jsonb({t}.*) AS row"""), {"o": org_id, "i": issuer_id}).scalars().all()
        if rows:
            gone[t] = rows
    if not gone:
        raise NothingToWithdraw(f"your organisation holds no data of its own about {name}")
    write_audit(session, org_id=org_id, actor_user_id=actor_user_id, action="issuer.client_data_withdrawn",
                target_type="issuer", target_id=issuer_id,
                detail={"issuer": name, "reason": why, "rows": json.loads(json.dumps(gone, default=str))})
    return {"issuer_id": issuer_id, "issuer": name, "reason": why, "withdrawn": {t: len(r) for t, r in gone.items()}}
