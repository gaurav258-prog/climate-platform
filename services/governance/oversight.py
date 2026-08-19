"""Supervisor's-eye rollup — the whole institution on one screen, the way a regulator/board would review it:
every mandatory filing with its status, coverage and KRI breaches, plus house-in-order readiness and open
exceptions. Composed entirely from existing org-scoped services (no new data), so it stays honest.
"""
from __future__ import annotations

from sqlalchemy.orm import Session


def supervisor_view(session: Session, org_id: str, org_type: str | None) -> dict:
    from services.governance.datapoint_catalog import coverage
    from services.governance.exception_monitor import exceptions
    from services.governance.filings import reporting_requirements
    from services.governance.kri import kri, kri_frameworks
    from services.governance.readiness import org_readiness

    reqs = reporting_requirements(session, org_id, org_type)
    kfw = {f["framework"] for f in kri_frameworks(org_type)}
    frameworks, total_breaches, never_filed = [], 0, 0
    for r in reqs:
        fw = r["framework"]
        cov = coverage(fw) or {}
        breaches = None
        breach_kris: list[str] = []
        if fw in kfw:
            try:
                k = kri(session, org_id, fw)
                breaches = k.get("breaches") or 0
                breach_kris = [x["label"] for x in (k.get("kpis") or []) if x.get("breached")]
                total_breaches += breaches
            except Exception:
                breaches = None
        last = r.get("last_filed")
        if not last:
            never_filed += 1
        frameworks.append({
            "framework": fw, "label": r.get("official_name") or r.get("label"),
            "regulator": r.get("regulator"), "due_label": r.get("due_label"),
            "last_filed": last, "n_filings": r.get("n_filings", 0),
            "coverage_pct": cov.get("pct_computed"),
            "breaches": breaches, "breach_kris": breach_kris,
        })

    rd = org_readiness(session, org_id, org_type)
    exc = exceptions(session, org_id)
    exc_summary = exc.get("summary") or {}
    n_exceptions = exc_summary.get("open", len(exc.get("exceptions") or []))
    # Institution-level view: the SAME finding (e.g. a completeness check) can fire on several live filings that
    # share one book. The Control Tower keeps those per-filing (each is separately trackable); here we collapse
    # identical findings into one row with an "affects N filings" count, so the board view isn't visually
    # repetitive. Order is preserved (already sorted blocking-first by the monitor).
    top: list[dict] = []
    seen: dict[tuple, dict] = {}
    for it in (exc.get("exceptions") or []):
        key = (it.get("category"), it.get("message"))
        if key in seen:
            seen[key]["filings_affected"] += 1
            continue
        row = {**it, "filings_affected": 1}
        seen[key] = row
        top.append(row)
    return {
        "frameworks": frameworks,
        "readiness": {"passed": rd.get("passed", 0), "total": rd.get("total", 0), "checks": rd.get("checks", [])},
        "exceptions": {"open": n_exceptions, "top": top[:6], "summary": exc_summary},
        "summary": {
            "n_frameworks": len(frameworks),
            "never_filed": never_filed,
            "total_breaches": total_breaches,
            "open_exceptions": n_exceptions,
            "readiness_pct": round(100 * rd.get("passed", 0) / rd.get("total", 1)) if rd.get("total") else 0,
        },
    }
