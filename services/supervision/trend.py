"""Trend, timeliness and anchor coverage — the second-period views of the supervisory workspace.

Trend: every submitted template on file for an entity, period by period — totals, sensitive share, the Tier-1
verdicts at that period's basis, and each cell's share across periods with the change since the previous one.
Timeliness: each expected framework filing against its obligation's due date, from what the platform records
(a filing's release moment is the time its record reached a filed status — stated as such, not as a regulator's
receipt stamp), plus how long after period end the template reached the supervisor's intake.
Anchor coverage: how many hazards actually carry a standing score at each scenario × horizon on the population's
cells — the honest label for the scenario chart.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import text

FILED = ("submitted", "accepted", "approved", "attested", "released")
MOVE_PP = 10.0    # a cell's share moving more than this between periods is worth a look


def list_submissions(session, regulator_org_id: str, subject_org_id: str, framework: str, template: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT DISTINCT ON (period_label) period_label, basis, cells, n_cells, source_file, created_at
        FROM supervisor_submissions
        WHERE regulator_org_id = CAST(:r AS uuid) AND subject_org_id = CAST(:s AS uuid) AND framework = :fw AND template = :tp
        ORDER BY period_label, created_at DESC
    """), {"r": regulator_org_id, "s": subject_org_id, "fw": framework, "tp": template}).mappings().all()
    out = [dict(r) | {"created_at": r["created_at"].isoformat()} for r in rows]
    out.sort(key=lambda r: r["period_label"])
    return out


def _share(cells: dict) -> tuple[float, float, Optional[float]]:
    gross = sum(float(c.get("gross_carrying_amount_eur") or 0) for c in cells.values())
    sens = sum(float(c.get("sensitive_physical_eur") or 0) for c in cells.values())
    return gross, sens, (round(100.0 * sens / gross, 1) if gross else None)


def pivot_cells(periods: list[dict]) -> list[dict]:
    """periods = [{period_label, cells}] sorted → one row per cell with its share and gross per period and the
    change (percentage points) between the last two periods it appears in."""
    labels = [p["period_label"] for p in periods]
    rows: dict[str, dict] = {}
    for p in periods:
        for key, c in (p["cells"] or {}).items():
            r = rows.setdefault(key, {"key": key, "geography": c.get("geography"), "sector": c.get("sector"), "share_pct": {}, "gross_eur": {}})
            g = float(c.get("gross_carrying_amount_eur") or 0)
            r["gross_eur"][p["period_label"]] = round(g)
            r["share_pct"][p["period_label"]] = round(100.0 * float(c.get("sensitive_physical_eur") or 0) / g, 1) if g else None
    out = []
    for r in rows.values():
        seen = [lb for lb in labels if lb in r["share_pct"] and r["share_pct"][lb] is not None]
        if len(seen) >= 2:
            r["change_pp"] = round(r["share_pct"][seen[-1]] - r["share_pct"][seen[-2]], 1)
            r["moved"] = abs(r["change_pp"]) > MOVE_PP
        else:
            r["change_pp"], r["moved"] = None, False
        r["in_periods"] = seen
        out.append(r)
    out.sort(key=lambda r: (-(abs(r["change_pp"]) if r["change_pp"] is not None else -1), -(max(r["gross_eur"].values() or [0]))))
    return out


def entity_trend(session, regulator_org_id: str, subject_org_id: str, spec: dict, scenario: str, horizon: str) -> dict:
    from services.supervision.plausibility import assess_entity
    ss = spec["submission"]
    subs = list_submissions(session, regulator_org_id, subject_org_id, ss["framework"], ss["template"])
    periods = []
    for s in subs:
        gross, sens, share = _share(s["cells"] or {})
        basis = s.get("basis") or {}
        sc, hz = basis.get("scenario") or scenario, basis.get("horizon") or horizon
        try:
            counts = assess_entity(session, regulator_org_id, subject_org_id, s["cells"] or {}, sc, hz)["counts"]
        except Exception:
            counts = None
        periods.append({"period_label": s["period_label"], "received_at": s["created_at"], "source_file": s.get("source_file"),
                        "n_cells": s.get("n_cells"), "gross_eur": round(gross), "sensitive_eur": round(sens), "share_pct": share,
                        "basis": {"scenario": sc, "horizon": hz, "stated": bool(basis.get("scenario"))}, "tier1_counts": counts})
    cells = pivot_cells([{"period_label": s["period_label"], "cells": s["cells"]} for s in subs])
    latest, prev = (periods[-1] if periods else None), (periods[-2] if len(periods) >= 2 else None)
    return {"periods": periods, "cells": cells, "labels": [p["period_label"] for p in periods],
            "latest": latest["period_label"] if latest else None, "previous": prev["period_label"] if prev else None,
            "change_pp": (round(latest["share_pct"] - prev["share_pct"], 1) if latest and prev and latest["share_pct"] is not None and prev["share_pct"] is not None else None),
            "n_moved": sum(1 for c in cells if c["moved"]),
            "note": "Shares are the entity's own submitted figures per period; the Tier-1 verdicts are judged at each period's stated basis. "
                    "One period on file means no trend yet — nothing is extrapolated."}


def population_trend(session, regulator_org_id: str, entities: list[dict], cfg: dict) -> dict:
    from services.supervision.profiles import sector_config
    rows = []
    for e in entities:
        sec = sector_config(cfg, e["type"])
        if not sec or not sec.get("intake"):
            continue
        ss = sec["intake"]["submission"]
        subs = list_submissions(session, regulator_org_id, e["org_id"], ss["framework"], ss["template"])
        shares = [(s["period_label"], _share(s["cells"] or {})[2]) for s in subs]
        latest = shares[-1] if shares else (None, None)
        prev = shares[-2] if len(shares) >= 2 else (None, None)
        rows.append({"org_id": e["org_id"], "name": e["name"], "periods": [p for p, _ in shares],
                     "latest_period": latest[0], "latest_share_pct": latest[1], "previous_period": prev[0], "previous_share_pct": prev[1],
                     "change_pp": (round(latest[1] - prev[1], 1) if latest[1] is not None and prev[1] is not None else None)})
    rows.sort(key=lambda r: -(abs(r["change_pp"]) if r["change_pp"] is not None else -1))
    return {"entities": rows, "n_with_trend": sum(1 for r in rows if r["change_pp"] is not None),
            "note": "Sensitive share of the submitted template, latest period against the previous one. Entities with one period on file show no change."}


def classify(due: Optional[date], filed_at: Optional[date], today: Optional[date] = None) -> tuple[str, Optional[int]]:
    """→ (state, days). Pure. States: filed_on_time, filed_late, outstanding_overdue, not_yet_due, no_due_date."""
    today = today or date.today()
    if filed_at is not None:
        if due is None:
            return "filed", None
        d = (filed_at - due).days
        return ("filed_late", d) if d > 0 else ("filed_on_time", -d)
    if due is None:
        return "no_due_date", None
    d = (today - due).days
    return ("outstanding_overdue", d) if d > 0 else ("not_yet_due", -d)


def timeliness(session, regulator_org_id: str, entities: list[dict], cfg: dict) -> dict:
    from services.governance import filings as F
    from services.supervision.profiles import sector_config
    ids = [e["org_id"] for e in entities]
    if not ids:
        return {"rows": [], "summary": {}}
    obligations = session.execute(text("""
        SELECT org_id::text AS org_id, framework, period_label, period_end, due_date FROM regulatory_obligation
        WHERE org_id = ANY(CAST(:ids AS uuid[]))"""), {"ids": ids}).mappings().all()
    due_by = {(o["org_id"], o["framework"], o["period_label"]): o for o in obligations}
    filings = session.execute(text("""
        SELECT DISTINCT ON (org_id, framework, period_label) org_id::text AS org_id, framework, period_label, period_end, status, updated_at, created_at
        FROM regulatory_filing WHERE org_id = ANY(CAST(:ids AS uuid[]))
        ORDER BY org_id, framework, period_label, (status = ANY(CAST(:filed AS text[]))) DESC, updated_at DESC
    """), {"ids": ids, "filed": list(FILED)}).mappings().all()
    filing_by = {(f["org_id"], f["framework"], f["period_label"]): f for f in filings}
    intake = session.execute(text("""
        SELECT subject_org_id::text AS org_id, framework, period_label, min(created_at) AS received_at FROM supervisor_submissions
        WHERE regulator_org_id = CAST(:r AS uuid) AND subject_org_id = ANY(CAST(:ids AS uuid[])) GROUP BY 1, 2, 3
    """), {"r": regulator_org_id, "ids": ids}).mappings().all()
    intake_by = {(i["org_id"], i["period_label"]): i["received_at"] for i in intake}
    rows = []
    for e in entities:
        sec = sector_config(cfg, e["type"])
        keys = {(e["org_id"], fw["framework"], pl) for fw in F.available_frameworks(e["type"]) for pl in
                {k[2] for k in list(due_by) + list(filing_by) if k[0] == e["org_id"] and k[1] == fw["framework"]}}
        for org_id, fw, pl in sorted(keys):
            ob, fl = due_by.get((org_id, fw, pl)), filing_by.get((org_id, fw, pl))
            filed_at = fl["updated_at"].date() if fl and fl["status"] in FILED else None
            state, days = classify(ob["due_date"] if ob else None, filed_at)
            period_end = (ob or fl or {}).get("period_end")
            received = intake_by.get((org_id, pl))
            rows.append({"org_id": org_id, "name": e["name"], "framework": fw, "framework_label": next((x["label"] for x in F.available_frameworks(e["type"]) if x["framework"] == fw), fw),
                         "period_label": pl, "period_end": period_end.isoformat() if period_end else None, "due_date": ob["due_date"].isoformat() if ob else None,
                         "status": fl["status"] if fl else None, "filed_at": filed_at.isoformat() if filed_at else None, "state": state, "days": days,
                         "intake_received_at": received.isoformat() if received else None,
                         "intake_lag_days": ((received.date() - period_end).days if received and period_end else None),
                         "in_profile": sec is not None})
    order = {"outstanding_overdue": 0, "filed_late": 1, "not_yet_due": 2, "filed_on_time": 3, "filed": 4, "no_due_date": 5}
    rows.sort(key=lambda r: (order.get(r["state"], 9), -(r["days"] or 0)))
    summary = {k: sum(1 for r in rows if r["state"] == k) for k in order}
    return {"rows": rows, "summary": summary, "as_of": datetime.now(timezone.utc).date().isoformat(),
            "note": "A filing counts as released when its record reached a filed status in the entity's workspace; the moment shown is that record's "
                    "last change, not a receipt stamp from the authority. Due dates come from the entity's obligations calendar."}


def anchor_coverage(session, entities: list[dict]) -> dict:
    """Hazards with a standing score at each scenario × horizon on the population's own cells."""
    ids = [e["org_id"] for e in entities]
    if not ids:
        return {"anchors": [], "hazards_today": 0}
    rows = session.execute(text("""
        SELECT c.scenario, c.time_horizon, count(DISTINCT c.hazard_type) AS n, array_agg(DISTINCT c.hazard_type) AS hazards
        FROM canonical_scores c
        WHERE c.score_lane = 'standing' AND c.valid_to IS NULL
          AND c.h3_cell IN (SELECT DISTINCT h3_cell FROM portfolio_entities WHERE org_id = ANY(CAST(:ids AS uuid[])) AND h3_cell IS NOT NULL)
        GROUP BY 1, 2
    """), {"ids": ids}).mappings().all()
    today = next((r["n"] for r in rows if r["scenario"] == "baseline" and r["time_horizon"] == "current"), 0)
    return {"anchors": [{"scenario": r["scenario"], "horizon": r["time_horizon"], "hazards": int(r["n"]), "hazard_list": sorted(r["hazards"])} for r in rows],
            "hazards_today": int(today),
            "note": "Number of hazards carrying a standing score at each scenario × horizon on the population's cells. Anchors with fewer hazards than today "
                    "are read on fewer channels — the chart says so rather than pretending the anchors are alike."}
