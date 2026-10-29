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

from services.governance.money_format import presentation_of
from services.governance.report_snapshots import get_snapshot

_SAME_PERIOD_TOL = 0.02   # a restatement should keep the headline within 2%
_PRIOR_JUMP_TOL = 0.40    # >40% period-over-period swing → confirm it's real


def _shared_figures(framework: str, payload: dict) -> dict:
    """The canonical headline figures a filing shares with its siblings (name → euro/number)."""
    if framework == "bank_tcfd":                       # the Taxonomy report shares only its book with its siblings (E95)
        return {k: v for k, v in {"total book value": (payload.get("rollup") or {}).get("total_value_eur")}.items() if v}
    if framework == "bank_p3esg":
        r = payload.get("rollup") or {}
        out = {"total book value": r.get("total_value_eur"), "value at risk": r.get("value_at_risk_eur")}
        from services.governance.pillar3_t1 import RECORD
        if RECORD in payload:                          # Template 1 total row, column i, on the stated method (E103)
            from services.governance.pillar3_report import t1_total
            et = (t1_total(payload) or {}).get("i")
        else:
            from services.scoring.pcaf import financed_total
            et = financed_total(payload.get("financed_emissions_tco2e") or {})
        if et:
            out["financed emissions (tCO₂e)"] = et
        return {k: v for k, v in out.items() if v}
    if framework == "reit_tcfd":
        r = payload.get("rollup") or {}
        return {k: v for k, v in {"property book value": r.get("total_value_eur"),
                                  "net operating income impact (%)": r.get("portfolio_noi_impact_pct")}.items() if v}
    if framework == "insurer_climate":
        r = payload.get("rollup") or {}
        return {k: v for k, v in {"sum insured": r.get("total_sum_insured_eur"),
                                  "expected annual loss": r.get("total_expected_annual_loss_eur")}.items() if v}
    if framework == "sfdr_pai":
        ent = payload.get("entity") or {}
        return {k: v for k, v in {"net asset value in scope": ent.get("total_value_eur")}.items() if v}
    return {}


def _f(rule, severity, passed, code, **params):
    """A cross-report finding in the catalogue's words (filing.check.cross.*): `msg` for the checklist, `message` its
    sentence for the other readers (as services.governance.filing_validation._check)."""
    from core import messages
    m = messages.render(code, **params)
    return {"rule": rule, "category": "cross_report", "severity": severity, "passed": passed,
            "message": m["detail"]["what"], "msg": m, "ref": None}


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

    from services.governance.filings import _role_match
    rows = session.execute(text(f"""
        SELECT rf.filing_id::text AS filing_id, rf.period_end, rf.period_label, rf.status,
               rf.snapshot_id::text AS snapshot_id, rs.version
        FROM regulatory_filing rf JOIN report_snapshots rs ON rs.snapshot_id = rf.snapshot_id
        WHERE rf.org_id = :o AND rf.framework = :fw AND rf.filing_id <> :f AND rf.snapshot_id IS NOT NULL
              AND rf.entity_id IS NOT DISTINCT FROM CAST(:ent AS uuid)
              AND {_role_match("rf", "CAST(:ent AS uuid)", "CAST(:role AS text)")}
        ORDER BY rf.period_end DESC, rf.seq DESC
    """), {"o": org_id, "fw": framework, "f": filing["filing_id"], "ent": filing.get("entity_id"),
           "role": filing.get("filing_role")}).mappings().all()
    # siblings are the same reporting entity's filings (fixed 2026-09-26: a solo filing was reconciled against the
    # whole organisation's, raising false "unusually large swing" warnings) — and of the same of its reports (E348: an
    # undertaking's own report is not its group's)

    same_period = next((r for r in rows if r["period_end"].isoformat() == period_end), None)
    prior_period = next((r for r in rows if r["period_end"].isoformat() < period_end), None)

    out: list[dict] = []
    if not same_period and not prior_period:
        out.append(_f("cross_report:none", "info", True, "filing.check.cross.none"))
        return out

    def compare(sib, kind, tol, verb):
        sib_snap = get_snapshot(session, org_id, sib["snapshot_id"])
        if not sib_snap:
            return
        cc, sc = presentation_of(snap.get("payload")), presentation_of(sib_snap.get("payload"))
        if cc != sc:                       # figures in different currencies can't be compared (multi-currency phase 3)
            out.append(_f(f"cross_report:{kind}:currency", "info", True, "filing.check.cross.currency",
                          period=sib["period_label"], version=sib["version"], other=sc, this=cc))
            return
        sib_figs = _shared_figures(framework, sib_snap.get("payload") or {})
        for name, cur_v in cur.items():
            sv = sib_figs.get(name)
            if not sv:
                continue
            rel = abs(cur_v - sv) / max(abs(sv), 1)
            ok = rel <= tol
            pct = round(rel * 100, 1)
            code = f"filing.check.cross.{kind}_{'ok' if ok else 'fail'}"
            out.append(_f(f"cross_report:{kind}:{name}", "info" if ok else "warning", ok, code,
                          figure=name[:1].upper() + name[1:], version=sib["version"], period=sib["period_label"], pct=pct))

    if same_period:
        compare(same_period, "same", _SAME_PERIOD_TOL, "restatement")
    if prior_period:
        compare(prior_period, "prior", _PRIOR_JUMP_TOL, "prior period")
    return out
