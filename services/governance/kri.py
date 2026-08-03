"""Key Regulatory Indicator (KRI) dashboard — the regulator's-eye consolidated risk view.

One place for the headline physical-risk indicators of the book: how much value sits at High+ risk, the
share of the book, coverage, financed emissions and taxonomy eligibility, plus the same figures over the
org's filed history so a trend is visible. Current figures come from the live engine (the same source the
disclosure uses); the history comes from the immutable filed snapshots, so the trend is auditable.
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.orm import Session


def _kpi(key, label, value, fmt, tone=None, hint=None):
    return {"key": key, "label": label, "value": value, "fmt": fmt, "tone": tone, "hint": hint}


def kri(session: Session, org_id: str, framework: str) -> dict:
    if framework == "bank_tcfd":
        return _bank_kri(session, org_id)
    if framework == "sfdr_pai":
        return _sfdr_kri(session, org_id)
    return {"framework": framework, "supported": False,
            "message": "KRI dashboard is available for the TCFD and SFDR frameworks."}


def _snapshot_history(session: Session, org_id: str, framework: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT rs.version, rs.reporting_basis, rs.payload, rf.period_label
        FROM report_snapshots rs
        JOIN regulatory_filing rf ON rf.snapshot_id = rs.snapshot_id
        WHERE rs.org_id = :o AND rs.report_type = :fw
        ORDER BY rf.period_end, rs.version
    """), {"o": org_id, "fw": framework}).mappings().all()
    out = []
    for r in rows:
        p = r["payload"]
        if isinstance(p, str):
            p = json.loads(p)
        out.append({"label": f'{r["period_label"]} v{r["version"]}', "payload": p})
    return out


def _bank_kri(session: Session, org_id: str) -> dict:
    from api.routers.bank import build_disclosure_snapshot
    from services.governance.reporting_settings import get_settings
    s = get_settings(session, org_id)
    snap = build_disclosure_snapshot(session, org_id, s["scenario"], s["horizon"])
    r = snap.get("rollup", {})
    em = snap.get("financed_emissions_tco2e", {})
    tax = snap.get("taxonomy", {})
    total = r.get("total_value_eur", 0) or 0
    elig = (tax.get("eligible") or {}).get("value_eur", 0) or 0
    tax_total = sum((v or {}).get("value_eur", 0) or 0 for v in tax.values())
    cov = round(100 * r.get("n_scored", 0) / r.get("n_assets", 1), 1) if r.get("n_assets") else 0

    kpis = [
        _kpi("total_value", "Total book value", total, "eur"),
        _kpi("value_at_risk", "Value at risk (High+)", r.get("value_at_risk_eur"), "eur", tone="#fb7185",
             hint="Value of the book in the top two severity bands"),
        _kpi("pct_at_risk", "Share at risk", r.get("pct_value_at_risk"), "pct", tone="#f0a860"),
        _kpi("coverage", "Book scored", cov, "pct", hint="Share of assets scored on the golden source"),
        _kpi("fin_emissions", "Financed emissions", sum((em.get(k) or 0) for k in ("scope1", "scope2", "scope3")),
             "num", hint="tCO₂e · PCAF-attributed"),
        _kpi("taxonomy", "EU-Taxonomy eligible", round(100 * elig / tax_total, 1) if tax_total else 0, "pct"),
    ]
    by_hazard = sorted(
        [{"hazard": h, "value": b.get("exposed_value_eur", 0), "score": b.get("max_score", 0)}
         for h, b in (snap.get("by_hazard") or {}).items() if (b.get("exposed_value_eur") or 0) > 0],
        key=lambda x: -x["value"])
    history = [{"label": h["label"],
                "total_value": (h["payload"].get("rollup") or {}).get("total_value_eur"),
                "value_at_risk": (h["payload"].get("rollup") or {}).get("value_at_risk_eur"),
                "pct_at_risk": (h["payload"].get("rollup") or {}).get("pct_value_at_risk")}
               for h in _snapshot_history(session, org_id, "bank_tcfd")]
    return {"framework": "bank_tcfd", "supported": True, "label": "TCFD physical-risk KRIs",
            "kpis": kpis, "by_hazard": by_hazard, "history": history}


def _sfdr_kri(session: Session, org_id: str) -> dict:
    from ml.regulatory.sfdr_pai import entity_pai_statement
    st = entity_pai_statement(session, org_id)
    if st.get("error"):
        return {"framework": "sfdr_pai", "supported": True, "label": "SFDR KRIs", "kpis": [],
                "by_hazard": [], "history": [], "note": st["error"]}
    ent = st.get("entity", {})
    cs = st.get("coverage_summary", {})
    kpis = [
        _kpi("nav", "NAV in scope", ent.get("total_value_eur"), "eur"),
        _kpi("positions", "Positions", ent.get("positions"), "num"),
        _kpi("indicators", "PAI indicators computed", cs.get("computed"), "num",
             hint=f'of {cs.get("mandatory_indicators")} mandatory'),
        _kpi("emissions_cov", "Emissions coverage", cs.get("emissions_coverage_pct"), "pct",
             tone="#f0a860" if (cs.get("emissions_coverage_pct") or 0) < 50 else None),
    ]
    history = [{"label": h["label"],
                "total_value": (h["payload"].get("entity") or {}).get("total_value_eur"),
                "value_at_risk": None, "pct_at_risk": None}
               for h in _snapshot_history(session, org_id, "sfdr_pai")]
    return {"framework": "sfdr_pai", "supported": True, "label": "SFDR entity KRIs",
            "kpis": kpis, "by_hazard": [], "history": history}
