"""General-ledger reconciliation — the second half of gate 4, 'reconcile to the ledger'.

The platform already ties every reported figure to its golden source; this ties the reported book TOTAL back
to the customer's GL control accounts, so a variance surfaces here (with a tolerance) rather than in an exam.
GL balances are uploaded in dated batches (one file = one batch); reconciliation uses the latest batch and the
same point-in-time book the engine computes (baseline / current). Nothing is invented — a variance is shown
honestly, '—' where no GL has been provided.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

VERTICAL = {"bank": "banking", "asset_manager": "assetmgmt", "insurer": "insurance", "reit": "realestate"}
TOLERANCE_PCT = 0.5   # within 0.5% of the GL counts as reconciled


def ingest(session: Session, org_id: str, rows: list[dict], user_id: Optional[str]) -> dict:
    """One upload = one dated batch. rows: {account_code, account_name, balance_eur, control_for?, as_of_date?}."""
    bid = str(uuid.uuid4())
    n = 0
    for r in rows:
        code = str(r.get("account_code") or "").strip()
        try:
            bal = float(str(r.get("balance_eur")).replace(",", "").replace("€", "").strip())
        except (TypeError, ValueError, AttributeError):
            continue
        if not code:
            continue
        session.execute(text("""
            INSERT INTO gl_balance (gl_id, org_id, batch_id, account_code, account_name, balance_eur, control_for, as_of_date, uploaded_by)
            VALUES (CAST(:g AS uuid), CAST(:o AS uuid), CAST(:b AS uuid), :code, :name, :bal, :cf, CAST(:asof AS date), CAST(:u AS uuid))
        """), {"g": str(uuid.uuid4()), "o": org_id, "b": bid, "code": code[:60],
               "name": str(r.get("account_name") or "")[:200], "bal": bal,
               "cf": (str(r.get("control_for")).strip() or "book") if r.get("control_for") else "book",
               "asof": (str(r.get("as_of_date")).strip() or None) if r.get("as_of_date") else None, "u": user_id})
        n += 1
    session.commit()
    return {"batch_id": bid, "rows": n}


def _latest_batch(session: Session, org_id: str):
    return session.execute(text("""
        SELECT batch_id::text AS b, max(as_of_date) AS asof
        FROM gl_balance WHERE org_id = CAST(:o AS uuid)
        GROUP BY batch_id ORDER BY max(uploaded_at) DESC LIMIT 1
    """), {"o": org_id}).mappings().first()


def reconciliation(session: Session, org_id: str, org_type: str) -> dict:
    vertical = VERTICAL.get(org_type)
    batch = _latest_batch(session, org_id)
    if not vertical:
        return {"available": False, "reason": "unsupported_sector"}
    if not batch:
        return {"available": False, "reason": "no_gl_uploaded"}
    accounts = session.execute(text("""
        SELECT account_code, account_name, CAST(balance_eur AS FLOAT) AS balance_eur, control_for
        FROM gl_balance WHERE org_id = CAST(:o AS uuid) AND batch_id = CAST(:b AS uuid)
        ORDER BY balance_eur DESC
    """), {"o": org_id, "b": batch["b"]}).mappings().all()
    gl_total = sum(a["balance_eur"] for a in accounts if (a["control_for"] or "book") == "book")
    from services.portfolio_engine import fetch_entities_with_risk
    rows = fetch_entities_with_risk(session, org_id, vertical, "baseline", "current")
    reported = sum((r.get("primary_value_eur") or 0) for r in rows)
    var = reported - gl_total
    var_pct = round(100 * var / gl_total, 3) if gl_total else None
    return {
        "available": True, "as_of": batch["asof"].isoformat() if batch["asof"] else None,
        "reported_book_eur": round(reported), "gl_book_eur": round(gl_total),
        "variance_eur": round(var), "variance_pct": var_pct, "tolerance_pct": TOLERANCE_PCT,
        "reconciled": (abs(var_pct) <= TOLERANCE_PCT) if var_pct is not None else False,
        "n_accounts": len(accounts), "accounts": [dict(a) for a in accounts],
    }
