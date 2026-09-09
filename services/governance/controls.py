"""Reporting control register — every automated reporting check the platform runs, named as a control and tested
on record.

The register (data/reference/reporting_controls.json) is configuration: objective, category, type, frequency, the
rule ids the control is made of, the evidence it leaves, the regulatory expectation it answers. This module tests
each control for one organisation from the evidence the platform already holds (validation findings on live
filings, readiness checks, feed refresh log, approval requests, model registry, breach episodes, source snapshots,
obligations) and records the outcome of every test, so operating effectiveness has a history: a pass rate over a
window, the last failure, the owner and the review date. Tested daily by the sweep and on demand. Nothing here
names a sector: a control applies to every tenant unless the register restricts it.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy import text

REGISTER_PATH = Path(__file__).resolve().parents[2] / "data" / "reference" / "reporting_controls.json"


def register() -> dict:
    d = json.loads(REGISTER_PATH.read_text())
    return {"version": d["version"], "categories": d["categories"], "controls": d["controls"]}


def control(control_id: str) -> Optional[dict]:
    return next((c for c in register()["controls"] if c["id"] == control_id), None)


# ── evidence gathered once per test run ─────────────────────────────────────────────────────────────────────
def _evidence(session, org_id: str, org_type: Optional[str]) -> dict:
    from services.data.feeds import feed_freshness
    from services.governance.filing_validation import validate_filing
    from services.governance.readiness import org_readiness
    from services.mlops.model_governance import PUBLISH_GATE_R2, registry
    filings = session.execute(text("""SELECT filing_id::text AS filing_id, framework, period_label, period_end, status, approval_request_id::text AS approval_request_id
                                      FROM regulatory_filing WHERE org_id = CAST(:o AS uuid) AND status <> 'superseded' ORDER BY created_at DESC"""), {"o": org_id}).mappings().all()
    findings: dict[str, list[dict]] = {}          # rule → [{filing, framework, period, passed, message, severity}]
    for f in filings:
        try:
            v = validate_filing(session, org_id, f["filing_id"])
        except Exception:
            continue
        for x in v["findings"]:
            key = "cross_report:*" if x["rule"].startswith("cross_report") else x["rule"]
            findings.setdefault(key, []).append({"filing_id": f["filing_id"], "framework": f["framework"], "period": f["period_label"], "passed": x["passed"],
                                                 "severity": x["severity"], "message": x["message"]})
    rd = org_readiness(session, org_id, org_type)
    readiness = {c["key"]: c for c in rd["checks"]}
    feeds = feed_freshness(session)
    models = registry(session)
    breaches = session.execute(text("""SELECT framework, kri_key, label, severity, onset_at, acknowledged_at FROM kri_breach_episode
                                       WHERE org_id = CAST(:o AS uuid) AND cleared_at IS NULL"""), {"o": org_id}).mappings().all()
    last_scan = session.execute(text("SELECT max(checked_at) FROM reg_source_snapshot")).scalar()
    obligations = session.execute(text("""SELECT o.framework, o.period_label, o.due_date,
                                                 EXISTS (SELECT 1 FROM regulatory_filing rf WHERE rf.org_id = o.org_id AND rf.framework = o.framework
                                                         AND rf.period_label = o.period_label AND rf.status IN ('submitted', 'accepted')) AS met
                                          FROM regulatory_obligation o WHERE o.org_id = CAST(:o AS uuid) AND o.due_date < CURRENT_DATE"""), {"o": org_id}).mappings().all()
    return {"filings": [dict(f) for f in filings], "findings": findings, "readiness": readiness, "feeds": feeds, "models": models, "gate": PUBLISH_GATE_R2,
            "breaches": [dict(b) for b in breaches], "last_scan": last_scan, "obligations": [dict(o) for o in obligations], "org_type": org_type}


# ── evaluators: each returns (outcome, n_items, n_failed, detail) ───────────────────────────────────────────
def _from_findings(ev: dict, rules: list[str]):
    items = [x for r in rules for x in ev["findings"].get(r, [])]
    if not items:
        return "not_applicable", 0, 0, [{"note": "No live filing to test against."}]
    failed = [x for x in items if not x["passed"]]
    return ("fail" if failed else "pass"), len(items), len(failed), [{"filing_id": x["filing_id"], "framework": x["framework"], "period": x["period"], "message": x["message"], "severity": x["severity"]} for x in failed[:20]]


def _from_readiness(ev: dict, keys: list[str]):
    checks = [ev["readiness"][k] for k in keys if k in ev["readiness"]]
    if not checks:
        return "not_applicable", 0, 0, [{"note": "This check does not apply to the organisation's sector."}]
    failed = [c for c in checks if not c["ok"]]
    return ("fail" if failed else "pass"), len(checks), len(failed), [{"check": c["label"], "hint": c.get("hint")} for c in failed]


def _approval_on_release(ev: dict):
    released = [f for f in ev["filings"] if f["status"] in ("submitted", "accepted", "approved")]
    if not released:
        return "not_applicable", 0, 0, [{"note": "Nothing released yet."}]
    failed = [f for f in released if not f["approval_request_id"]]
    out = "fail" if failed else "pass"
    # the second-approver readiness check is part of the same control
    sa = ev["readiness"].get("second_approver")
    if sa and not sa["ok"]:
        out = "fail"; failed = failed + [{"framework": "—", "period": "—", "note": sa["label"]}]
    return out, len(released) + (1 if sa else 0), len(failed), [{"framework": f["framework"], "period": f.get("period_label") or f.get("period"), "note": f.get("note") or "released without an approval request"} for f in failed[:20]]


def _feeds(ev: dict):
    bad = [f for f in ev["feeds"] if f["status"] in ("overdue", "failed")]
    return ("fail" if bad else "pass"), len(ev["feeds"]), len(bad), [{"feed": f.get("name") or f.get("key"), "status": f["status"], "last_refresh": f.get("last_refresh")} for f in bad]


def _models(ev: dict):
    active = [m for m in ev["models"] if m.get("is_active")]
    if not active:
        return "not_applicable", 0, 0, [{"note": "No active model in the registry."}]
    # a euro-publishing model must meet the gate; a screening model (no r²) is allowed only as screening
    bad = [m for m in active if m.get("r2_oos") is not None and float(m["r2_oos"]) < ev["gate"]]
    cal = ev["readiness"].get("calibrations_current")
    n_failed = len(bad) + (1 if cal and not cal["ok"] else 0)
    detail = [{"hazard": m["hazard_type"], "version": m["model_version"], "r2_oos": float(m["r2_oos"]), "gate": ev["gate"]} for m in bad]
    if cal and not cal["ok"]:
        detail.append({"check": cal["label"], "hint": cal.get("hint")})
    return ("fail" if n_failed else "pass"), len(active) + (1 if cal else 0), n_failed, detail


def _breaches(ev: dict):
    now = datetime.now(timezone.utc)
    reds = [b for b in ev["breaches"] if b["severity"] == "red"]
    if not reds:
        return "pass", 0, 0, [{"note": "No open red breach."}]
    late = [b for b in reds if not b["acknowledged_at"] and b["onset_at"] and (now - b["onset_at"]).days > 7]
    return ("fail" if late else "pass"), len(reds), len(late), [{"framework": b["framework"], "indicator": b["label"], "onset_at": b["onset_at"].isoformat()} for b in late]


def _reg_scan(ev: dict):
    ls = ev["last_scan"]
    if not ls:
        return "fail", 1, 1, [{"note": "No source scan on record."}]
    age = (datetime.now(timezone.utc) - ls).days
    return ("pass" if age <= 7 else "fail"), 1, (0 if age <= 7 else 1), [{"last_scan": ls.isoformat(), "days_ago": age}]


def _obligations(ev: dict):
    if not ev["obligations"]:
        return "pass", 0, 0, [{"note": "No obligation past its due date."}]
    missed = [o for o in ev["obligations"] if not o["met"]]
    return ("fail" if missed else "pass"), len(ev["obligations"]), len(missed), [{"framework": o["framework"], "period": o["period_label"], "due_date": o["due_date"].isoformat()} for o in missed[:20]]


_RULE_EVALUATORS: dict[str, Callable] = {
    "approval_on_release": _approval_on_release, "golden_source_fresh": _feeds, "publish_gate": _models, "red_breach_acknowledged": _breaches,
    "reg_scan_recent": _reg_scan, "obligation_met": _obligations}
_READINESS_KEYS = {"second_approver", "identity", "inputs_high_quality", "sites_scored", "calibrations_current", "golden_source_fresh"}


def evaluate(ev: dict, c: dict):
    rules = c["rules"]
    special = [r for r in rules if r in _RULE_EVALUATORS]
    if special:
        return _RULE_EVALUATORS[special[0]](ev)
    if all(r in _READINESS_KEYS for r in rules):
        return _from_readiness(ev, rules)
    return _from_findings(ev, rules)


# ── test run ────────────────────────────────────────────────────────────────────────────────────────────────
def test_all(session, *, org_id: str, org_type: Optional[str], actor_user_id: Optional[str], trigger: str) -> dict:
    reg = register()
    ev = _evidence(session, org_id, org_type)
    results = []
    for c in reg["controls"]:
        if c.get("sectors") and org_type not in c["sectors"]:
            continue
        try:
            outcome, n, nf, detail = evaluate(ev, c)
        except Exception as e:           # a control whose evidence cannot be read is a failed test, never a silent pass
            outcome, n, nf, detail = "fail", 1, 1, [{"note": f"could not test: {type(e).__name__}: {e}"}]
        results.append({"control_id": c["id"], "outcome": outcome, "n_items": n, "n_failed": nf, "detail": detail})
    n_pass = sum(1 for r in results if r["outcome"] == "pass"); n_fail = sum(1 for r in results if r["outcome"] == "fail"); n_na = len(results) - n_pass - n_fail
    run_id = session.execute(text("""INSERT INTO control_test_run (org_id, trigger, actor_user_id, n_controls, n_pass, n_fail, n_na, register_version)
                                     VALUES (CAST(:o AS uuid), :t, CAST(:u AS uuid), :n, :p, :f, :na, :v) RETURNING run_id::text"""),
                             {"o": org_id, "t": trigger, "u": actor_user_id, "n": len(results), "p": n_pass, "f": n_fail, "na": n_na, "v": reg["version"]}).scalar()
    for r in results:
        session.execute(text("""INSERT INTO control_test_result (run_id, org_id, control_id, outcome, n_items, n_failed, detail)
                                VALUES (CAST(:r AS uuid), CAST(:o AS uuid), :c, :out, :n, :nf, CAST(:d AS jsonb))"""),
                        {"r": run_id, "o": org_id, "c": r["control_id"], "out": r["outcome"], "n": r["n_items"], "nf": r["n_failed"], "d": json.dumps(r["detail"], default=str)})
    if trigger == "manual":
        from api.services.rbac import write_audit
        write_audit(session, org_id=org_id, actor_user_id=actor_user_id, action="controls.tested", target_type="control_test_run", target_id=run_id,
                    detail={"n_controls": len(results), "pass": n_pass, "fail": n_fail, "not_applicable": n_na, "register_version": reg["version"]})
    return {"run_id": run_id, "n_controls": len(results), "pass": n_pass, "fail": n_fail, "not_applicable": n_na, "results": results}


def sweep_all(session) -> dict:
    """Daily: test every tenant's controls so operating effectiveness accrues without anyone opening the register."""
    orgs = session.execute(text("SELECT org_id::text AS org_id, type FROM organizations WHERE type NOT IN ('platform', 'regulator')")).mappings().all()
    roll = {"orgs": 0, "fail": 0}
    for o in orgs:
        try:
            r = test_all(session, org_id=o["org_id"], org_type=o["type"], actor_user_id=None, trigger="sweep")
            session.commit()
        except Exception:
            session.rollback(); continue
        roll["orgs"] += 1; roll["fail"] += r["fail"]
    return roll


# ── the register as the organisation sees it ────────────────────────────────────────────────────────────────
def view(session, org_id: str, window_days: int = 90) -> dict:
    reg = register()
    latest = {r["control_id"]: dict(r) for r in session.execute(text("""
        SELECT DISTINCT ON (control_id) control_id, outcome, n_items, n_failed, detail, at FROM control_test_result
        WHERE org_id = CAST(:o AS uuid) ORDER BY control_id, at DESC""" ), {"o": org_id}).mappings().all()}
    rates = {r["control_id"]: dict(r) for r in session.execute(text("""
        SELECT control_id, count(*) FILTER (WHERE outcome <> 'not_applicable') AS n_tests, count(*) FILTER (WHERE outcome = 'pass') AS n_pass,
               max(at) FILTER (WHERE outcome = 'fail') AS last_fail
        FROM control_test_result WHERE org_id = CAST(:o AS uuid) AND at >= now() - make_interval(days => :w) GROUP BY control_id"""), {"o": org_id, "w": window_days}).mappings().all()}
    owners = {r["control_id"]: dict(r) for r in session.execute(text("""
        SELECT co.control_id, co.owner_user_id::text AS owner_user_id, u.full_name AS owner, co.review_by, co.note FROM control_owner co
        LEFT JOIN users u ON u.user_id = co.owner_user_id WHERE co.org_id = CAST(:o AS uuid)"""), {"o": org_id}).mappings().all()}
    rows = []
    for c in reg["controls"]:
        lt, rt, ow = latest.get(c["id"]), rates.get(c["id"]), owners.get(c["id"])
        rows.append({**c, "category_label": reg["categories"].get(c["category"], c["category"]),
                     "last": {"outcome": lt["outcome"], "n_items": lt["n_items"], "n_failed": lt["n_failed"], "detail": lt["detail"], "at": lt["at"].isoformat()} if lt else None,
                     "pass_rate_pct": (round(100.0 * rt["n_pass"] / rt["n_tests"], 1) if rt and rt["n_tests"] else None), "n_tests": rt["n_tests"] if rt else 0,
                     "last_fail": rt["last_fail"].isoformat() if rt and rt["last_fail"] else None,
                     "owner": ow["owner"] if ow else None, "owner_user_id": ow["owner_user_id"] if ow else None, "review_by": ow["review_by"].isoformat() if ow and ow["review_by"] else None,
                     "review_overdue": bool(ow and ow["review_by"] and ow["review_by"] < date.today()), "owner_note": ow["note"] if ow else None})
    last_run = session.execute(text("SELECT at, trigger, n_pass, n_fail, n_na FROM control_test_run WHERE org_id = CAST(:o AS uuid) ORDER BY at DESC LIMIT 1"), {"o": org_id}).mappings().first()
    return {"register_version": reg["version"], "categories": reg["categories"], "controls": rows, "window_days": window_days,
            "last_run": (dict(last_run) | {"at": last_run["at"].isoformat()}) if last_run else None,
            "summary": {"controls": len(rows), "pass": sum(1 for r in rows if r["last"] and r["last"]["outcome"] == "pass"), "fail": sum(1 for r in rows if r["last"] and r["last"]["outcome"] == "fail"),
                        "not_applicable": sum(1 for r in rows if r["last"] and r["last"]["outcome"] == "not_applicable"), "untested": sum(1 for r in rows if not r["last"]),
                        "unowned": sum(1 for r in rows if not r["owner"]), "reviews_overdue": sum(1 for r in rows if r["review_overdue"])}}


def history(session, org_id: str, control_id: str, limit: int = 60) -> list[dict]:
    rows = session.execute(text("""SELECT r.at, r.outcome, r.n_items, r.n_failed, r.detail, t.trigger FROM control_test_result r JOIN control_test_run t ON t.run_id = r.run_id
                                   WHERE r.org_id = CAST(:o AS uuid) AND r.control_id = :c ORDER BY r.at DESC LIMIT :l"""), {"o": org_id, "c": control_id, "l": limit}).mappings().all()
    return [dict(r) | {"at": r["at"].isoformat()} for r in rows]


def set_owner(session, *, org_id: str, control_id: str, owner_user_id: Optional[str], review_by: Optional[date], note: Optional[str], actor_user_id: str) -> None:
    if not control(control_id):
        raise ValueError("No such control.")
    if owner_user_id:
        ok = session.execute(text("SELECT 1 FROM users WHERE user_id = CAST(:u AS uuid) AND org_id = CAST(:o AS uuid) AND status = 'active'"), {"u": owner_user_id, "o": org_id}).scalar()
        if not ok:
            raise ValueError("The owner must be an active user of this organisation.")
    session.execute(text("""INSERT INTO control_owner (org_id, control_id, owner_user_id, review_by, note, updated_by)
                            VALUES (CAST(:o AS uuid), :c, CAST(:u AS uuid), :r, :n, CAST(:a AS uuid))
                            ON CONFLICT (org_id, control_id) DO UPDATE SET owner_user_id = EXCLUDED.owner_user_id, review_by = EXCLUDED.review_by, note = EXCLUDED.note,
                                                                           updated_by = EXCLUDED.updated_by, updated_at = now()"""),
                    {"o": org_id, "c": control_id, "u": owner_user_id, "r": review_by, "n": (note or "").strip() or None, "a": actor_user_id})
    from api.services.rbac import write_audit
    write_audit(session, org_id=org_id, actor_user_id=actor_user_id, action="controls.owner_set", target_type="control", target_id=control_id,
                detail={"owner_user_id": owner_user_id, "review_by": review_by.isoformat() if review_by else None})


# ── exports ─────────────────────────────────────────────────────────────────────────────────────────────────
def register_csv(v: dict) -> bytes:
    import csv
    import io
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["Control", "Label", "Category", "Type", "Frequency", "Objective", "Rules", "Evidence", "Regulatory anchor", "Owner", "Review by", "Last outcome", "Last tested", "Items", "Failed", f"Pass rate {v['window_days']}d %", "Last failure"])
    for c in v["controls"]:
        lt = c["last"] or {}
        w.writerow([c["id"], c["label"], c["category_label"], c["type"], c["frequency"], c["objective"], "; ".join(c["rules"]), c["evidence"], c["anchor"], c["owner"] or "", c["review_by"] or "",
                    lt.get("outcome") or "untested", (lt.get("at") or "")[:16].replace("T", " "), lt.get("n_items", ""), lt.get("n_failed", ""), c["pass_rate_pct"] if c["pass_rate_pct"] is not None else "", (c["last_fail"] or "")[:10]])
    return buf.getvalue().encode("utf-8")


def register_summary(session, org_id: str) -> dict:
    """What the board pack and assurance pack carry: counts, failing controls and untested/unowned ones."""
    v = view(session, org_id)
    return {"register_version": v["register_version"], "summary": v["summary"], "last_run": v["last_run"],
            "failing": [{"id": c["id"], "label": c["label"], "n_failed": c["last"]["n_failed"], "owner": c["owner"]} for c in v["controls"] if c["last"] and c["last"]["outcome"] == "fail"],
            "untested_or_unowned": [{"id": c["id"], "label": c["label"], "untested": not c["last"], "unowned": not c["owner"]} for c in v["controls"] if not c["last"] or not c["owner"]]}
