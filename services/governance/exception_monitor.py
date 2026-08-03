"""Exception Monitor — every open data/validation exception across all filings, in one place.

The validation engine already flags what's wrong inside a single filing. This sweeps EVERY live filing,
collects the failing checks (blocking + warning, including cross-report reconciliation), and presents them
as one prioritised worklist classified by criticality — so a preparer lands on the exceptions they must act
on rather than opening each filing. Each exception can be spun into an assignable task with one click, keyed
so it never duplicates. Nothing invented: an exception is a real failing check over a frozen snapshot.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

# failing severity → task criticality when spun into the board
_CRIT = {"blocking": "critical", "warning": "high"}


def exceptions(session: Session, org_id: str) -> dict:
    """All open exceptions across the org's live filings + a summary. An exception is a failing check."""
    from services.governance.filing_validation import validate_filing

    filings = session.execute(text("""
        SELECT filing_id::text AS filing_id, framework, period_label, status
        FROM regulatory_filing
        WHERE org_id = :o AND status <> 'superseded' AND snapshot_id IS NOT NULL
        ORDER BY created_at DESC
    """), {"o": org_id}).mappings().all()

    # which (filing, rule) already have a live task, so the UI can show "tracked"
    tracked = {r[0] for r in session.execute(text("""
        SELECT source_ref FROM regulatory_task
        WHERE org_id = :o AND source IN ('validation','exception') AND status NOT IN ('done','cancelled')
              AND source_ref IS NOT NULL
    """), {"o": org_id}).all()}

    items: list[dict] = []
    for f in filings:
        try:
            res = validate_filing(session, org_id, f["filing_id"])
        except Exception:  # noqa: BLE001 — a filing that can't validate shouldn't sink the whole monitor
            continue
        for finding in res["findings"]:
            if finding["passed"] or finding["severity"] not in _CRIT:
                continue
            ref = f"{f['filing_id']}:{finding['rule']}"
            items.append({
                "filing_id": f["filing_id"], "filing_label": f["framework"], "period": f["period_label"],
                "filing_status": f["status"], "rule": finding["rule"], "category": finding["category"],
                "severity": finding["severity"], "criticality": _CRIT[finding["severity"]],
                "message": finding["message"], "source_ref": ref, "tracked": ref in tracked,
            })

    order = {"blocking": 0, "warning": 1}
    items.sort(key=lambda x: (order.get(x["severity"], 9), x["category"]))
    by_cat: dict[str, int] = {}
    for it in items:
        by_cat[it["category"]] = by_cat.get(it["category"], 0) + 1
    return {
        "exceptions": items,
        "summary": {
            "total": len(items),
            "blocking": sum(1 for i in items if i["severity"] == "blocking"),
            "warnings": sum(1 for i in items if i["severity"] == "warning"),
            "tracked": sum(1 for i in items if i["tracked"]),
            "by_category": by_cat,
            "filings_scanned": len(filings),
        },
    }


def spin_task(session: Session, org_id: str, actor: str, *, filing_id: str, rule: str,
              message: str, severity: str, assignee_user_id: str | None = None) -> dict:
    """Turn an exception into an assignable task (de-duped by filing:rule)."""
    from services.governance.tasks import create_task
    crit = _CRIT.get(severity, "normal")
    return create_task(session, org_id, actor, title=message, criticality=crit,
                       filing_id=filing_id, source="validation", source_ref=f"{filing_id}:{rule}",
                       assignee_user_id=assignee_user_id)
