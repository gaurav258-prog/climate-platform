"""Model-risk register — a model card for every model the organisation's figures rest on, and its own review record.

A card is assembled from what the platform already holds: the model registry (version, algorithm, lifecycle,
approval and activation), the validation ledger (latest run: method, target, samples, skill grade, gate), the
Fidelity presentation, the feeds behind the hazard with their freshness, the calibration and validation notes,
and — for the economic-impact models — the crop calibration fits with their out-of-sample r². The organisation
adds the one thing only it can: an independent review by name (fit for use / restricted use / not fit) bound to
the hash of the card it reviewed, with a next-review date. Register and cards export for the auditor and the
supervisor. The card never claims more than the ledger shows: a model without a validation run says so, a
screening model is labelled screening, a fit below the publish floor is held.
"""
from __future__ import annotations

import hashlib
import io
import json
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import text

CONCLUSIONS = {"fit_for_use": "Fit for its stated use", "restricted_use": "Fit for use with restrictions (see comment)", "not_fit": "Not fit for use"}
USE = {"score": "Physical-risk score per located asset (the score lane behind every filing, KRI and decision)",
       "impact": "Economic impact of a hazard on a commodity origin (euro at risk in the agri-food product line)"}


def canonical_json(c: dict) -> bytes:
    return json.dumps(c, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def sha256(c: dict) -> str:
    return hashlib.sha256(canonical_json(c)).hexdigest()


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


# ── cards ───────────────────────────────────────────────────────────────────────────────────────────────────
def _score_cards(session) -> list[dict]:
    from ml.validation.fidelity import fidelity
    from services.data.feeds import feeds_for_hazard
    from services.mlops.model_governance import PUBLISH_GATE_R2
    from services.validation.engine import latest_skill_for_model
    rows = session.execute(text("""SELECT model_id::text AS model_id, model_version, hazard_type, algorithm, lifecycle_status, is_active, r2_oos, validation_auc, validation_avg_precision,
                                          training_data_vintage, training_cell_count, calibration_note, validation_note, approved_by, approved_at, activated_by, activated_at, retired_at, superseded_by::text AS superseded_by, created_at
                                   FROM model_registry WHERE lifecycle_status IN ('active', 'approved', 'challenger', 'candidate') AND hazard_type <> 'loop_test'
                                   ORDER BY hazard_type, is_active DESC, created_at DESC""")).mappings().all()
    events = {}
    for e in session.execute(text("SELECT model_id::text AS model_id, from_status, to_status, actor, reason, r2_oos, created_at FROM model_status_event ORDER BY created_at")).mappings().all():
        events.setdefault(e["model_id"], []).append({"from": e["from_status"], "to": e["to_status"], "actor": e["actor"], "reason": e["reason"], "r2_oos": float(e["r2_oos"]) if e["r2_oos"] is not None else None, "at": _iso(e["created_at"])})
    # hazard-level evidence: the validation ledger's latest run per hazard (when no run is linked to the model
    # version) and the honest coverage map (event-catalogue backtests, economic validation, what is still pending)
    from services.intelligence.model_validation import validation_coverage
    cov = {i["hazard"]: i for i in validation_coverage(session)["items"]}
    by_hazard = {}
    for v in session.execute(text("""SELECT DISTINCT ON (hazard_type) hazard_type, kind, method, target_source, n_samples, skill_grade, passed_gate, metrics, created_at
                                     FROM validation_run ORDER BY hazard_type, (COALESCE(metrics->>'applicable', 'true') = 'true') DESC, created_at DESC""")).mappings().all():
        by_hazard[v["hazard_type"]] = dict(v)
    feeds_cache: dict[str, list] = {}
    out = []
    for r in rows:
        hz = r["hazard_type"]
        if hz not in feeds_cache:
            feeds_cache[hz] = feeds_for_hazard(session, hz)
        skill = latest_skill_for_model(session, r["model_id"])
        r2 = float(r["r2_oos"]) if r["r2_oos"] is not None else None
        auc = float(r["validation_auc"]) if r["validation_auc"] is not None else None
        hv = by_hazard.get(hz)
        cv = cov.get(hz)
        if skill:
            m = skill.get("metrics") or {}
            fid = fidelity(skill["kind"], r2_oos=m.get("r2_oos", r2), spearman=m.get("spearman"), auc=m.get("auc", auc))
            validation = {"level": "model", "kind": skill["kind"], "skill_grade": skill["skill_grade"], "passed_gate": bool(skill["passed_gate"]), "metrics": m, "at": _iso(skill["created_at"])}
        elif hv:
            m = hv.get("metrics") or {}
            fid = fidelity(hv["kind"], r2_oos=m.get("r2_oos", r2), spearman=m.get("spearman"), auc=m.get("auc", auc))
            validation = {"level": "hazard", "kind": hv["kind"], "method": hv["method"], "target": hv["target_source"], "n_samples": hv["n_samples"], "skill_grade": hv["skill_grade"],
                          "passed_gate": bool(hv["passed_gate"]), "metrics": m, "at": _iso(hv["created_at"]), "note": "Evidence recorded at hazard level, not linked to this model version."}
        elif cv and cv["status"] == "validated":
            sp = None
            if "Spearman" in (cv.get("detail") or ""):
                try:
                    sp = float(cv["detail"].split("Spearman")[-1].strip().split()[0])
                except ValueError:
                    sp = None
            fid = fidelity("rank", spearman=sp, auc=auc) if sp is not None else (fidelity("regression", r2_oos=r2) if r2 is not None else None)
            validation = {"level": "hazard", "kind": "rank" if sp is not None else "regression", "method": cv["method"], "detail": cv.get("detail"), "strength": cv.get("strength"),
                          "passed_gate": None, "note": "Backtest recorded in the model-validation surface at hazard level."}
        else:
            fid = fidelity("regression", r2_oos=r2) if r2 is not None else None
            validation = None
        pending = (cv or {}).get("needed") if (cv and cv["status"] != "validated") else None
        tier = "calibrated" if (r2 is not None and r2 >= PUBLISH_GATE_R2) else ("screening" if r["is_active"] or r["lifecycle_status"] == "approved" else "candidate")
        claim = ("Publishes a euro figure: out-of-sample r² meets the 0.40 gate." if tier == "calibrated" else
                 "Screening signal only: no euro figure is published on this model." if tier == "screening" else "Not in use: candidate or challenger under evaluation.")
        out.append({"ref": f"model:{r['model_id']}", "kind": "score", "hazard": hz, "name": r["model_version"], "algorithm": r["algorithm"], "lifecycle": r["lifecycle_status"], "active": bool(r["is_active"]),
                    "tier": tier, "claim": claim, "use": USE["score"], "r2_oos": r2, "auc": auc, "gate": PUBLISH_GATE_R2, "fidelity": fid, "validation": validation,
                    "data": {"training_vintage": _iso(r["training_data_vintage"]), "training_cells": r["training_cell_count"], "feeds": feeds_cache[hz]},
                    "limitations": [x for x in (r["calibration_note"], r["validation_note"], (f"Coverage note: {pending}" if pending else None)) if x],
                    "governance": {"approved_by": r["approved_by"], "approved_at": _iso(r["approved_at"]), "activated_by": r["activated_by"], "activated_at": _iso(r["activated_at"]),
                                   "retired_at": _iso(r["retired_at"]), "superseded_by": r["superseded_by"], "registered_at": _iso(r["created_at"]), "events": events.get(r["model_id"], [])},
                    "controls": ["C-MOD-01"]})
    return out


def _impact_cards(session) -> list[dict]:
    from ml.validation.fidelity import fidelity
    from services.intelligence.supply_cogs import RANGED_PUBLISH_FLOOR
    rows = session.execute(text("""SELECT c.name AS commodity, c.commodity_id::text AS commodity_id, f.origin, f.region_key, f.hazard_driver, f.season_months, f.spei_scale, f.fit_version,
                                          CAST(f.r2 AS FLOAT) AS r2, CAST(f.r2_oos AS FLOAT) AS r2_oos, f.n_years, f.baseline_from, f.baseline_to, f.source_note, f.created_at,
                                          cal.calibration_tier, cal.scoring_model, cal.impact_version, cal.sensitivity
                                   FROM sc_commodity_fit f JOIN sc_commodities c ON c.commodity_id = f.commodity_id
                                   LEFT JOIN v_sc_commodity_calibration cal ON cal.commodity_id = f.commodity_id AND cal.origin = f.origin
                                   WHERE f.region_key IS NOT NULL AND f.hazard_driver IS NOT NULL ORDER BY c.name, f.origin""")).mappings().all()
    chal = {(x["commodity_id"], x["origin"], x["hazard_driver"]): dict(x) for x in session.execute(text(
        "SELECT commodity_id::text AS commodity_id, origin, hazard_driver, verdict, method, challenger_version, mean_abs_divergence_pp, computed_at FROM sc_commodity_challenger")).mappings().all()}
    out = []
    for r in rows:
        published = r["r2_oos"] is not None and r["r2_oos"] >= RANGED_PUBLISH_FLOOR
        ch = chal.get((r["commodity_id"], r["origin"], r["hazard_driver"]))
        out.append({"ref": f"calibration:{r['commodity_id']}:{r['origin']}:{r['hazard_driver']}", "kind": "impact", "hazard": r["hazard_driver"], "name": f"{r['commodity']} · {r['origin']} · {r['hazard_driver']}",
                    "algorithm": f"{r['scoring_model'] or 'ranged fit'} ({r['fit_version'] or 'fit'})", "lifecycle": "published" if published else "held", "active": published,
                    "tier": (r["calibration_tier"] or ("ranged" if published else "indicative")), "claim": ("Publishes a euro BAND with the r² stated." if published else f"Held: out-of-sample r² below the {RANGED_PUBLISH_FLOOR:.2f} floor — never a euro."),
                    "use": USE["impact"], "r2_oos": r["r2_oos"], "r2_in_sample": r["r2"], "gate": RANGED_PUBLISH_FLOOR, "fidelity": fidelity("regression", r2_oos=r["r2_oos"]),
                    "validation": {"kind": "regression", "method": "leave-one-out cross-validation on observed yield", "n_years": r["n_years"], "baseline": f"{r['baseline_from']}–{r['baseline_to']}",
                                   "challenger": ({"verdict": ch["verdict"], "method": ch["method"], "version": ch["challenger_version"], "divergence_pp": float(ch["mean_abs_divergence_pp"]) if ch["mean_abs_divergence_pp"] is not None else None, "at": _iso(ch["computed_at"])} if ch else None)},
                    "data": {"region": r["region_key"], "season_months": r["season_months"], "spei_scale": r["spei_scale"], "source": r["source_note"]},
                    "limitations": ["A climate-attributable model needs a climate-attributable target: the fit explains yield only through the named driver; policy, war, water management and prices are out of scope."],
                    "governance": {"impact_version": r["impact_version"], "sensitivity": float(r["sensitivity"]) if r["sensitivity"] is not None else None, "registered_at": _iso(r["created_at"]), "events": []},
                    "controls": ["C-MOD-01"]})
    return out


def cards(session, org_type: Optional[str]) -> list[dict]:
    out = _score_cards(session)
    if org_type in (None, "manufacturer"):
        out += _impact_cards(session)
    for c in out:
        c["card_sha256"] = sha256({k: v for k, v in c.items() if k != "card_sha256"})
    return out


# ── the register as the organisation sees it ────────────────────────────────────────────────────────────────
def _reviews(session, org_id: str) -> dict[str, dict]:
    rows = session.execute(text("""SELECT DISTINCT ON (model_ref) model_ref, review_id::text AS review_id, u.full_name AS reviewer, conclusion, comment, evidence_sha256, next_review_by, reviewed_at
                                   FROM model_risk_review r JOIN users u ON u.user_id = r.reviewer_user_id WHERE r.org_id = CAST(:o AS uuid) ORDER BY model_ref, reviewed_at DESC"""), {"o": org_id}).mappings().all()
    return {r["model_ref"]: dict(r) | {"next_review_by": _iso(r["next_review_by"]), "reviewed_at": _iso(r["reviewed_at"]), "conclusion_label": CONCLUSIONS.get(r["conclusion"], r["conclusion"])} for r in rows}


def view(session, org_id: str, org_type: Optional[str]) -> dict:
    cs = cards(session, org_type)
    rv = _reviews(session, org_id)
    today = date.today()
    for c in cs:
        r = rv.get(c["ref"])
        c["review"] = r
        c["review_state"] = ("none" if not r else "stale" if r["evidence_sha256"] != c["card_sha256"] else "overdue" if (r["next_review_by"] and r["next_review_by"] < today.isoformat()) else "current")
    active = [c for c in cs if c["active"]]
    return {"cards": cs, "conclusions": CONCLUSIONS,
            "summary": {"models": len(cs), "in_use": len(active), "calibrated": sum(1 for c in active if c["tier"] in ("calibrated", "ranged", "backtested")),
                        "screening": sum(1 for c in active if c["tier"] == "screening"), "unvalidated": sum(1 for c in active if c["kind"] == "score" and not c["validation"]),
                        "reviewed_current": sum(1 for c in active if c["review_state"] == "current"), "review_stale": sum(1 for c in active if c["review_state"] == "stale"),
                        "review_overdue": sum(1 for c in active if c["review_state"] == "overdue"), "unreviewed": sum(1 for c in active if c["review_state"] == "none")},
            "note": "A card states only what the ledger shows. 'Stale' means the model card changed since the review (new version, validation or lifecycle event) and needs a fresh review."}


def review(session, *, org_id: str, org_type: Optional[str], model_ref: str, actor: dict, conclusion: str, comment: Optional[str], next_review_by: Optional[date]) -> dict:
    if conclusion not in CONCLUSIONS:
        raise ValueError(f"Conclusion must be one of: {', '.join(CONCLUSIONS)}.")
    if conclusion != "fit_for_use" and not (comment or "").strip():
        raise ValueError("A restricted or not-fit conclusion needs a comment.")
    card = next((c for c in cards(session, org_type) if c["ref"] == model_ref), None)
    if not card:
        raise ValueError("No such model in the register.")
    rid = session.execute(text("""INSERT INTO model_risk_review (org_id, model_ref, reviewer_user_id, conclusion, comment, evidence_sha256, next_review_by)
                                  VALUES (CAST(:o AS uuid), :m, CAST(:u AS uuid), :c, :cm, :h, :n) RETURNING review_id::text"""),
                          {"o": org_id, "m": model_ref, "u": actor["id"], "c": conclusion, "cm": (comment or "").strip() or None, "h": card["card_sha256"], "n": next_review_by}).scalar()
    from api.services.rbac import write_audit
    write_audit(session, org_id=org_id, actor_user_id=actor["id"], action="model_risk.reviewed", target_type="model", target_id=model_ref,
                detail={"review_id": rid, "model": card["name"], "hazard": card["hazard"], "conclusion": conclusion, "card_sha256": card["card_sha256"], "next_review_by": _iso(next_review_by)})
    return {"review_id": rid, "card_sha256": card["card_sha256"]}


def history(session, org_id: str, model_ref: str) -> list[dict]:
    rows = session.execute(text("""SELECT review_id::text AS review_id, u.full_name AS reviewer, conclusion, comment, evidence_sha256, next_review_by, reviewed_at
                                   FROM model_risk_review r JOIN users u ON u.user_id = r.reviewer_user_id WHERE r.org_id = CAST(:o AS uuid) AND r.model_ref = :m ORDER BY reviewed_at DESC"""),
                           {"o": org_id, "m": model_ref}).mappings().all()
    return [dict(r) | {"next_review_by": _iso(r["next_review_by"]), "reviewed_at": _iso(r["reviewed_at"]), "conclusion_label": CONCLUSIONS.get(r["conclusion"], r["conclusion"])} for r in rows]


# ── exports ─────────────────────────────────────────────────────────────────────────────────────────────────
def register_csv(v: dict) -> bytes:
    import csv
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["Ref", "Kind", "Hazard", "Model", "Algorithm", "Lifecycle", "In use", "Tier", "Claim", "Out-of-sample r²", "Gate", "Fidelity", "Validation", "Approved by", "Activated", "Card hash", "Review", "Reviewer", "Reviewed", "Next review", "Review state"])
    for c in v["cards"]:
        val = c.get("validation") or {}
        r = c.get("review") or {}
        w.writerow([c["ref"], c["kind"], c["hazard"], c["name"], c["algorithm"], c["lifecycle"], "yes" if c["active"] else "no", c["tier"], c["claim"], c["r2_oos"] if c["r2_oos"] is not None else "", c["gate"],
                    (c["fidelity"] or {}).get("band_label") or "not testable", f"{val.get('kind') or ''} {val.get('skill_grade') or val.get('method') or ''}".strip() or "none on record",
                    (c["governance"] or {}).get("approved_by") or "", ((c["governance"] or {}).get("activated_at") or "")[:10], c["card_sha256"][:16],
                    r.get("conclusion_label") or "", r.get("reviewer") or "", (r.get("reviewed_at") or "")[:10], r.get("next_review_by") or "", c["review_state"]])
    return buf.getvalue().encode("utf-8")


def render_card_pdf(c: dict, org_name: str, reviews: list[dict]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm, title=f"Model card — {c['name']}", author=org_name)
    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=16, spaceAfter=4); H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, spaceBefore=9, spaceAfter=3)
    P = ParagraphStyle("p", parent=ss["BodyText"], fontSize=9, leading=12); S = ParagraphStyle("s", parent=P, fontSize=7.5, textColor=colors.HexColor("#555555"))
    grid = TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7.8), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bbbbbb")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9eef5")), ("VALIGN", (0, 0), (-1, -1), "TOP")])

    def table(rows, widths=None):
        t = Table([[Paragraph(str("" if v is None else v), S) for v in r] for r in rows], colWidths=widths, repeatRows=1); t.setStyle(grid); return t
    g, v, d = c["governance"] or {}, c.get("validation") or {}, c.get("data") or {}
    fid = c.get("fidelity") or {}
    x = [Paragraph(f"Model card — {c['name']}", H1), Paragraph(f"{org_name} · model-risk register · generated {datetime.now(timezone.utc).isoformat()[:16].replace('T', ' ')} UTC · card hash {c['card_sha256']}", S), Spacer(1, 6),
         Paragraph("1. Identity and use", H2),
         table([["Field", "Value"], ["Hazard / driver", c["hazard"]], ["Kind", "physical-risk score" if c["kind"] == "score" else "economic impact"], ["Algorithm", c["algorithm"]], ["Lifecycle", c["lifecycle"]],
                ["In use", "yes" if c["active"] else "no"], ["Tier", c["tier"]], ["What it may claim", c["claim"]], ["Used for", c["use"]]], [45 * mm, 125 * mm]),
         Paragraph("2. Validation", H2),
         Paragraph(v.get("note") or ("Validation is linked to this model version." if v else ""), S),
         table([["Field", "Value"], ["Out-of-sample r²", c["r2_oos"] if c["r2_oos"] is not None else "none on record"], ["Publish gate", c["gate"]],
                ["Fidelity", f"{fid.get('family_label', '')} {fid.get('symbol', '')} {fid.get('value', '—')} · {fid.get('band_label', 'not testable')}" if fid else "not testable"],
                ["Latest validation", (f"{v.get('kind', '')} · {v.get('method', '')} · {v.get('detail') or ''} · grade {v.get('skill_grade') or v.get('strength') or '—'} · {('passed' if v.get('passed_gate') else 'did not pass') + ' the gate' if v.get('passed_gate') is not None else 'no gate applies'} · {str(v.get('at', ''))[:10]}" if c["kind"] == "score" and v
                                       else f"{v.get('method', '')} · {v.get('n_years', '')} years · baseline {v.get('baseline', '')}" if v else "No validation run on record.")],
                ["Challenger", (f"{v['challenger']['method']} {v['challenger']['version']} · {v['challenger']['verdict']}" if v.get("challenger") else "none")]], [45 * mm, 125 * mm]),
         Paragraph("3. Data", H2),
         table([["Field", "Value"]] + [[k.replace("_", " "), (", ".join(f"{f['name']} ({f['status']})" for f in val) if k == "feeds" else val)] for k, val in d.items()], [45 * mm, 125 * mm]),
         Paragraph("4. Limitations", H2)] + [Paragraph(f"• {lim}", P) for lim in (c.get("limitations") or ["None recorded."])] + [
         Paragraph("5. Governance", H2),
         table([["Field", "Value"], ["Approved", f"{g.get('approved_by') or '—'} · {(g.get('approved_at') or '')[:10]}"], ["Activated", f"{g.get('activated_by') or '—'} · {(g.get('activated_at') or '')[:10]}"],
                ["Registered", (g.get("registered_at") or "")[:10]], ["Controls covering it", ", ".join(c.get("controls") or [])]], [45 * mm, 125 * mm])]
    if g.get("events"):
        x += [Spacer(1, 3), table([["When", "From", "To", "Actor", "Reason"]] + [[(e["at"] or "")[:16].replace("T", " "), e["from"] or "—", e["to"], e["actor"], e["reason"]] for e in g["events"]], [30 * mm, 22 * mm, 22 * mm, 30 * mm, 66 * mm])]
    x += [Paragraph("6. Independent review by the organisation", H2)]
    x += [table([["Reviewed", "Reviewer", "Conclusion", "Comment", "Next review", "Card reviewed"]] + [[(r["reviewed_at"] or "")[:10], r["reviewer"], r["conclusion_label"], r.get("comment") or "", r.get("next_review_by") or "", r["evidence_sha256"][:12]] for r in reviews],
                [22 * mm, 34 * mm, 40 * mm, 44 * mm, 20 * mm, 22 * mm])] if reviews else [Paragraph("No review recorded yet.", P)]
    doc.build(x)
    return buf.getvalue()
