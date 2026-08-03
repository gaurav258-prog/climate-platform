"""Cross-report reconciliation — do the shared figures in this filing agree with its siblings?

Within-filing tie-out (filing_validation) proves a filing is internally consistent. Cross-report checks
prove it is consistent with the OTHER filings that draw on the same book:

  • vs its restated predecessor (same period) — a restatement corrects specific figures, so the headline
    book/NAV should still reconcile closely; a whole-book swing is worth a second look.
  • vs the prior period (same framework) — a modest move is normal; an implausibly large swing is flagged
    for confirmation (continuity check), never blocked — a real book change is legitimate.

These are WARNING/INFO only: they surface in the validation card but never gate submission, because a
genuine change between periods must be allowed. Reads frozen snapshots on both sides, so the answer is stable.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.governance.report_snapshots import get_snapshot

_SAME_PERIOD_TOL = 0.02   # a restatement should keep the headline within 2%
_PRIOR_JUMP_TOL = 0.40    # >40% period-over-period swing → confirm it's real


def _shared_figures(framework: str, payload: dict) -> dict:
    """The canonical headline figures a filing shares with its siblings (name → euro/number)."""
    if framework == "bank_tcfd":
        r = payload.get("rollup") or {}
        em = payload.get("financed_emissions_tco2e") or {}
        out = {"total book value": r.get("total_value_eur"), "value at risk": r.get("value_at_risk_eur")}
        et = sum((em.get(k) or 0) for k in ("scope1", "scope2", "scope3"))
        if et:
            out["financed emissions (tCO₂e)"] = et
        return {k: v for k, v in out.items() if v}
    if framework == "reit_tcfd":
        r = payload.get("rollup") or {}
        return {k: v for k, v in {"property book value": r.get("total_value_eur"),
                                  "NOI impact %": r.get("portfolio_noi_impact_pct")}.items() if v}
    if framework == "insurer_climate":
        r = payload.get("rollup") or {}
        return {k: v for k, v in {"sum insured": r.get("total_sum_insured_eur"),
                                  "expected annual loss": r.get("total_expected_annual_loss_eur")}.items() if v}
    if framework == "sfdr_pai":
        ent = payload.get("entity") or {}
        return {k: v for k, v in {"NAV in scope": ent.get("total_value_eur")}.items() if v}
    return {}


def _f(rule, severity, passed, message):
    return {"rule": rule, "category": "cross_report", "severity": severity, "passed": passed,
            "message": message, "ref": None}


def cross_report_findings(session: Session, org_id: str, filing: dict) -> list[dict]:
    """Reconcile a filing's shared figures against its nearest same-period and prior-period siblings."""
    framework = filing["framework"]
    snap = filing.get("snapshot")
    if not snap:
        return []
    cur = _shared_figures(framework, snap.get("payload") or {})
    if not cur:
        return []
    period_end = filing["period_end"]

    rows = session.execute(text("""
        SELECT rf.filing_id::text AS filing_id, rf.period_end, rf.period_label, rf.status,
               rf.snapshot_id::text AS snapshot_id, rs.version
        FROM regulatory_filing rf JOIN report_snapshots rs ON rs.snapshot_id = rf.snapshot_id
        WHERE rf.org_id = :o AND rf.framework = :fw AND rf.filing_id <> :f AND rf.snapshot_id IS NOT NULL
        ORDER BY rf.period_end DESC, rf.created_at DESC
    """), {"o": org_id, "fw": framework, "f": filing["filing_id"]}).mappings().all()

    same_period = next((r for r in rows if r["period_end"].isoformat() == period_end), None)
    prior_period = next((r for r in rows if r["period_end"].isoformat() < period_end), None)

    out: list[dict] = []
    if not same_period and not prior_period:
        out.append(_f("cross_report:none", "info", True,
                      "No sibling filing to reconcile against — this is the first of its kind."))
        return out

    def compare(sib, kind, tol, verb):
        sib_snap = get_snapshot(session, org_id, sib["snapshot_id"])
        if not sib_snap:
            return
        sib_figs = _shared_figures(framework, sib_snap.get("payload") or {})
        for name, cur_v in cur.items():
            sv = sib_figs.get(name)
            if not sv:
                continue
            rel = abs(cur_v - sv) / max(abs(sv), 1)
            ok = rel <= tol
            pct = round(rel * 100, 1)
            if kind == "same":
                msg = (f"{name} reconciles with the same-period v{sib['version']} (Δ{pct}%)" if ok
                       else f"{name} differs from same-period v{sib['version']} by {pct}% — a restatement "
                            f"usually corrects specifics, not the whole book")
            else:
                msg = (f"{name} moved {pct}% vs {sib['period_label']} — within normal range" if ok
                       else f"{name} moved {pct}% vs {sib['period_label']} — an unusually large swing; confirm it's real")
            out.append(_f(f"cross_report:{kind}:{name}", "info" if ok else "warning", ok, msg))

    if same_period:
        compare(same_period, "same", _SAME_PERIOD_TOL, "restatement")
    if prior_period:
        compare(prior_period, "prior", _PRIOR_JUMP_TOL, "prior period")
    return out
