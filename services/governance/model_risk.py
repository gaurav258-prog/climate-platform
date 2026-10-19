"""Model-risk register — a model card for every model the organisation's figures rest on, and its own review record.

A card is assembled from what the platform already holds: the model registry (version, algorithm, lifecycle,
approval and activation), the validation ledger (latest run: design, observed record, samples, skill grade, gate),
the Fidelity presentation, the feeds behind the hazard, the hazard register's standing (core/hazard_taxonomy.py —
the one source of what a hazard's scores may claim) and — for the economic-impact models — the crop calibration fits
with their out-of-sample r². The organisation adds the one thing only it can: an independent review by name (fit for
use / restricted use / not fit) bound to the hash of the card it reviewed, with a next-review date. Register and cards
export for the auditor and the supervisor. The card never claims more than the ledger shows: a model without a
validation run says so, a fit below the publish floor is held.

A card is two things (UI standard, 2026-10-16): its FACTS — codes, numbers, dates, the record's identifiers — which the
review is bound to (card_sha256 hashes them, and nothing else), and their WORDS, rendered from the message catalogue
(core/messages.py) when the register is read: rewording the catalogue never makes a review stale, and neither does a
feed refreshing (a feed's freshness is shown, not hashed). The registry's engineers' notes (calibration_note,
validation_note, a fit's source_note) stay in the registry; the card's account of a hazard is the catalogue's.
"""
from __future__ import annotations

import hashlib
import io
import json
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import text

from core import messages
from core.errors import UserError

CONCLUSIONS = {"fit_for_use": "Fit for its stated use", "restricted_use": "Fit for use with restrictions (see comment)", "not_fit": "Not fit for use"}
# the card's words: everything a reader sees that is not a fact of the record (added by _words, never hashed)
WORDS = ("name", "hazard_name", "kind_name", "lifecycle_name", "method_name", "method_message", "standing_name",
         "standing_message", "claim", "use", "evidence", "basis", "limits", "feeds", "origin_name", "validation_names", "governance_names")


def canonical_json(c: dict) -> bytes:
    return json.dumps(c, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def sha256(c: dict) -> str:
    return hashlib.sha256(canonical_json(c)).hexdigest()


def facts_of(card: dict) -> dict:
    """What a review is bound to: the card's facts — never its words, its review, or its feeds' freshness."""
    return {k: v for k, v in card.items() if k not in WORDS and k not in ("card_sha256", "review", "review_state")}


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def _name(kind: str, key) -> Optional[str]:
    """A code's customer name from the catalogue, or None when it has none (the screen then says so)."""
    return messages.names().get(kind, {}).get(key) if key is not None else None


def _who(actor: Optional[str]) -> Optional[str]:
    """Who acted, as a reader names them: a person's name as recorded, or 'A platform process' for a process's own
    identifier (a code such as a backtest's name), which is internal language."""
    if actor and "_" in actor and actor == actor.lower() and " " not in actor:
        return messages.name("model.risk.actor", "process")
    return actor


def _pct(x: Optional[float]) -> str:
    return "—" if x is None else f"{round(100 * x)}%"


# ── cards: the facts ─────────────────────────────────────────────────────────────────────────────────────────────
def _score_cards(session) -> list[dict]:
    from ml.validation.fidelity import fidelity
    from services.data.feeds import feeds_for_hazard
    from services.intelligence.model_validation import hazard_for_channel, ledger_design
    from services.mlops.model_governance import PUBLISH_GATE_R2
    rows = session.execute(text("""SELECT model_id::text AS model_id, model_version, hazard_type, algorithm, lifecycle_status, is_active, r2_oos, validation_auc, validation_avg_precision,
                                          training_data_vintage, training_cell_count, approved_by, approved_at, activated_by, activated_at, retired_at, superseded_by::text AS superseded_by, created_at
                                   FROM model_registry WHERE lifecycle_status IN ('active', 'approved', 'challenger', 'candidate') AND hazard_type <> 'loop_test'
                                   ORDER BY hazard_type, is_active DESC, seq DESC""")).mappings().all()
    events = {}
    for e in session.execute(text("SELECT model_id::text AS model_id, from_status, to_status, actor, reason, r2_oos, created_at FROM model_status_event ORDER BY seq")).mappings().all():
        events.setdefault(e["model_id"], []).append({"from": e["from_status"], "to": e["to_status"], "actor": e["actor"], "reason": e["reason"], "r2_oos": float(e["r2_oos"]) if e["r2_oos"] is not None else None, "at": _iso(e["created_at"])})
    # the validation ledger, read in the order it was written (seq, E216): the latest run linked to each model version,
    # and the latest run per hazard (an applicable one first) for a version with none of its own
    by_model = {v["model_id"]: dict(v) for v in session.execute(text("""SELECT DISTINCT ON (model_id) model_id::text AS model_id, kind, method, target_source, n_samples, skill_grade, passed_gate, metrics, created_at
                                                                        FROM validation_run WHERE model_id IS NOT NULL ORDER BY model_id, seq DESC""")).mappings().all()}
    by_hazard = {v["hazard_type"]: dict(v) for v in session.execute(text("""SELECT DISTINCT ON (hazard_type) hazard_type, kind, method, target_source, n_samples, skill_grade, passed_gate, metrics, created_at
                                     FROM validation_run ORDER BY hazard_type, (COALESCE(metrics->>'applicable', 'true') = 'true') DESC, seq DESC""")).mappings().all()}
    feeds_cache: dict[str, list] = {}
    out = []
    for r in rows:
        hz = r["hazard_type"]
        if hz not in feeds_cache:
            feeds_cache[hz] = feeds_for_hazard(session, hz)
        r2 = float(r["r2_oos"]) if r["r2_oos"] is not None else None
        auc = float(r["validation_auc"]) if r["validation_auc"] is not None else None
        run, level = (by_model.get(r["model_id"]), "model") if r["model_id"] in by_model else (by_hazard.get(hz), "hazard")
        if run:
            m = run.get("metrics") or {}
            fid = fidelity(run["kind"], r2_oos=m.get("r2_oos", r2), spearman=m.get("spearman"), auc=m.get("auc", auc))
            validation = {"level": level, "kind": run["kind"], "method": run["method"], "design": ledger_design(hz, run["method"] or ""),
                          "record": run["target_source"], "n_samples": run["n_samples"], "skill_grade": run["skill_grade"],
                          "passed_gate": bool(run["passed_gate"]), "metrics": m, "at": _iso(run["created_at"])}
        else:
            fid = fidelity("regression", r2_oos=r2) if r2 is not None else None
            validation = None
        reg = hazard_for_channel(hz)
        out.append({"ref": f"model:{r['model_id']}", "kind": "score", "hazard": hz, "register_hazard": reg.id if reg else None,
                    "model": r["model_version"], "algorithm": r["algorithm"], "lifecycle": r["lifecycle_status"], "active": bool(r["is_active"]),
                    # what the hazard's scores may claim: the register's tier (one source), not a rule of this page
                    "standing": reg.tier.value if reg else None,
                    "r2_oos": r2, "auc": auc, "gate": PUBLISH_GATE_R2, "fidelity": fid, "validation": validation,
                    "data": {"training_vintage": _iso(r["training_data_vintage"]), "training_cells": r["training_cell_count"],
                             "feeds": [f["key"] for f in feeds_cache[hz]]},
                    "governance": {"approved_by": r["approved_by"], "approved_at": _iso(r["approved_at"]), "activated_by": r["activated_by"], "activated_at": _iso(r["activated_at"]),
                                   "retired_at": _iso(r["retired_at"]), "superseded_by": r["superseded_by"], "registered_at": _iso(r["created_at"]), "events": events.get(r["model_id"], [])},
                    "controls": ["C-MOD-01"], "_feeds": feeds_cache[hz]})
    return out


def _impact_cards(session) -> list[dict]:
    from ml.validation.fidelity import fidelity
    from services.intelligence.supply_cogs import RANGED_PUBLISH_FLOOR
    rows = session.execute(text("""SELECT c.name AS commodity, c.commodity_id::text AS commodity_id, f.origin, f.region_key, f.hazard_driver, f.season_months, f.spei_scale, f.fit_version,
                                          CAST(f.r2 AS FLOAT) AS r2, CAST(f.r2_oos AS FLOAT) AS r2_oos, f.n_years, f.baseline_from, f.baseline_to, f.created_at,
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
        out.append({"ref": f"calibration:{r['commodity_id']}:{r['origin']}:{r['hazard_driver']}", "kind": "impact", "hazard": r["hazard_driver"],
                    "commodity": r["commodity"], "origin": (r["origin"] or "").strip(), "model": r["fit_version"], "scoring_model": r["scoring_model"],
                    "algorithm": "ranged_fit", "lifecycle": "published" if published else "held", "active": published,
                    "standing": r["calibration_tier"] or ("ranged" if published else "indicative"),
                    "r2_oos": r["r2_oos"], "r2_in_sample": r["r2"], "gate": RANGED_PUBLISH_FLOOR, "fidelity": fidelity("regression", r2_oos=r["r2_oos"]),
                    "validation": {"level": "model", "kind": "regression", "method": "loo_cv", "design": "harvests", "n_years": r["n_years"],
                                   "baseline": [r["baseline_from"], r["baseline_to"]],
                                   "challenger": ({"verdict": ch["verdict"], "method": ch["method"], "version": ch["challenger_version"], "divergence_pp": float(ch["mean_abs_divergence_pp"]) if ch["mean_abs_divergence_pp"] is not None else None, "at": _iso(ch["computed_at"])} if ch else None)},
                    "data": {"region": r["region_key"], "season_months": r["season_months"], "spei_scale": r["spei_scale"]},
                    "governance": {"impact_version": r["impact_version"], "sensitivity": float(r["sensitivity"]) if r["sensitivity"] is not None else None, "registered_at": _iso(r["created_at"]), "events": []},
                    "controls": ["C-MOD-01"]})
    return out


def cards(session, org_type: Optional[str]) -> list[dict]:
    """Every card: its facts, the hash of those facts, then its words."""
    out = _score_cards(session)
    if org_type in (None, "manufacturer"):
        out += _impact_cards(session)
    origins = _origins(session, {c["origin"] for c in out if c.get("origin")})
    for c in out:
        feeds = c.pop("_feeds", [])
        c["card_sha256"] = sha256(facts_of(c))
        _words(c, feeds, origins)
    return out


def _origins(session, iso2: set[str]) -> dict[str, str]:
    from services.intelligence.model_validation import _origin_names
    return _origin_names(session, iso2)


# ── cards: the words (the catalogue's; never hashed) ───────────────────────────────────────────────────────────────
def _words(c: dict, feeds: list[dict], origins: dict[str, str]) -> None:
    v = c.get("validation") or {}
    c["hazard_name"] = _name("hazard", c["hazard"]) or _name("coverage.hazard", c.get("register_hazard"))
    c["kind_name"] = _name("model.risk.kind", c["kind"])
    c["lifecycle_name"] = _name("model.risk.lifecycle", c["lifecycle"])
    c["method_name"] = _name("model.risk.method", c["algorithm"])
    c["method_message"] = None if c["method_name"] else messages.render("model.risk.method.unnamed")
    g = c.get("governance") or {}
    c["governance_names"] = {"approved_by": _who(g.get("approved_by")), "activated_by": _who(g.get("activated_by")),
                             "events": [{"who": _who(e.get("actor")), "to": _name("model.risk.lifecycle", e.get("to")),
                                         "from": _name("model.risk.lifecycle", e.get("from"))} for e in g.get("events") or []]}
    c["feeds"] = [{"key": f["key"], "name": f["name"], "status": f.get("status"), "last_refresh": _iso(f.get("last_refresh"))} for f in feeds]
    c["validation_names"] = {"design": _name("validation.design", v.get("design")), "skill": _name("model.risk.skill", v.get("skill_grade")),
                             "verdict": _name("model.risk.verdict", (v.get("challenger") or {}).get("verdict"))} if v else None
    if c["kind"] == "score":
        c["name"] = c["hazard_name"]
        tier = messages.render(f"coverage.tier.{c['standing']}") if c.get("standing") else None
        c["standing_name"], c["standing_message"] = (tier["label"], tier) if tier else (None, None)
        c["claim"] = tier if (c["active"] and tier) else messages.render("model.risk.claim.not_in_use")
        c["use"] = messages.render("model.risk.use.score")
        c["evidence"] = messages.render(f"model.risk.evidence.{v['level']}" if v else "model.risk.evidence.none")
        # the Coverage page's account of the hazard, with the validation bars it quotes (services.intelligence.coverage)
        from services.intelligence.coverage import _gates
        c["basis"] = messages.render(f"coverage.hazard.{c['register_hazard']}", **_gates()) if c.get("register_hazard") else None
        c["limits"] = []
    else:
        c["origin_name"] = origins.get(c["origin"], c["origin"])
        c["name"] = f"{c['commodity']} · {c['origin_name']}"
        c["standing_name"] = _name("model.risk.impact_tier", c["standing"])
        c["standing_message"] = None
        floor = _pct(c["gate"])
        c["claim"] = (messages.render("model.risk.claim.untested") if c["r2_oos"] is None else
                      messages.render("model.risk.claim.range" if c["active"] else "model.risk.claim.held", r2=_pct(c["r2_oos"]), floor=floor))
        c["use"] = messages.render("model.risk.use.impact")
        c["evidence"] = messages.render("model.risk.evidence.model")
        c["basis"] = None
        c["limits"] = [messages.render("model.risk.limit.one_driver")]


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
    # may carry a figure: a score whose hazard the register holds validated, or a crop fit that publishes its range
    figure = [c for c in active if (c["kind"] == "score" and c.get("standing") == "calibrated") or (c["kind"] == "impact" and c["lifecycle"] == "published")]
    return {"cards": cs, "conclusions": CONCLUSIONS,
            "summary": {"models": len(cs), "in_use": len(active), "carries_figure": len(figure), "screens_only": len(active) - len(figure),
                        "unvalidated": sum(1 for c in active if c["kind"] == "score" and not c["validation"]),
                        "reviewed_current": sum(1 for c in active if c["review_state"] == "current"), "review_stale": sum(1 for c in active if c["review_state"] == "stale"),
                        "review_overdue": sum(1 for c in active if c["review_state"] == "overdue"), "unreviewed": sum(1 for c in active if c["review_state"] == "none")},
            "about": messages.render("model.risk.about")}


def review(session, *, org_id: str, org_type: Optional[str], model_ref: str, actor: dict, conclusion: str, comment: Optional[str], next_review_by: Optional[date]) -> dict:
    if conclusion not in CONCLUSIONS:
        raise UserError("model.risk.error.conclusion")
    if conclusion != "fit_for_use" and not (comment or "").strip():
        raise UserError("model.risk.error.comment")
    card = next((c for c in cards(session, org_type) if c["ref"] == model_ref), None)
    if not card:
        raise UserError("model.risk.error.no_model")
    rid = session.execute(text("""INSERT INTO model_risk_review (org_id, model_ref, reviewer_user_id, conclusion, comment, evidence_sha256, next_review_by)
                                  VALUES (CAST(:o AS uuid), :m, CAST(:u AS uuid), :c, :cm, :h, :n) RETURNING review_id::text"""),
                          {"o": org_id, "m": model_ref, "u": actor["id"], "c": conclusion, "cm": (comment or "").strip() or None, "h": card["card_sha256"], "n": next_review_by}).scalar()
    from api.services.rbac import write_audit
    write_audit(session, org_id=org_id, actor_user_id=actor["id"], action="model_risk.reviewed", target_type="model", target_id=model_ref,
                detail={"review_id": rid, "model": card["model"], "hazard": card["hazard"], "conclusion": conclusion, "card_sha256": card["card_sha256"], "next_review_by": _iso(next_review_by)})
    return {"review_id": rid, "card_sha256": card["card_sha256"]}


def history(session, org_id: str, model_ref: str) -> list[dict]:
    rows = session.execute(text("""SELECT review_id::text AS review_id, u.full_name AS reviewer, conclusion, comment, evidence_sha256, next_review_by, reviewed_at
                                   FROM model_risk_review r JOIN users u ON u.user_id = r.reviewer_user_id WHERE r.org_id = CAST(:o AS uuid) AND r.model_ref = :m ORDER BY reviewed_at DESC"""),
                           {"o": org_id, "m": model_ref}).mappings().all()
    return [dict(r) | {"next_review_by": _iso(r["next_review_by"]), "reviewed_at": _iso(r["reviewed_at"]), "conclusion_label": CONCLUSIONS.get(r["conclusion"], r["conclusion"])} for r in rows]


# ── exports: the same words as the screen ─────────────────────────────────────────────────────────────────────
def _validation_line(c: dict) -> str:
    v, n = c.get("validation") or {}, c.get("validation_names") or {}
    if not v:
        return c["evidence"]["label"]
    parts = [n.get("design") or "", n.get("skill") or "",
             ("passed its bar" if v.get("passed_gate") else "did not pass its bar") if v.get("passed_gate") is not None else "",
             str(v.get("at") or "")[:10]]
    return " · ".join(p for p in parts if p) + ("" if v.get("level") != "hazard" else " · tested at hazard level")


def register_csv(v: dict) -> bytes:
    import csv
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["Ref", "Kind", "Model", "Hazard", "Model reference", "Method", "Lifecycle", "In use", "Standing", "What it may claim",
                "Out-of-sample r²", "Gate", "Fidelity", "Validation", "Approved by", "Activated", "Card fingerprint", "Review", "Reviewer",
                "Reviewed", "Next review", "Review state"])
    for c in v["cards"]:
        r = c.get("review") or {}
        g = c.get("governance") or {}
        w.writerow([c["ref"], c["kind_name"], c["name"], c["hazard_name"], c["model"], c["method_name"] or c["algorithm"], c["lifecycle_name"],
                    "yes" if c["active"] else "no", c["standing_name"] or "", c["claim"]["label"], c["r2_oos"] if c["r2_oos"] is not None else "", c["gate"],
                    (c["fidelity"] or {}).get("band_label") or "not testable", _validation_line(c),
                    c["governance_names"]["approved_by"] or "", (g.get("activated_at") or "")[:10], c["card_sha256"][:16],
                    r.get("conclusion_label") or "", r.get("reviewer") or "", (r.get("reviewed_at") or "")[:10], r.get("next_review_by") or "",
                    {"none": "not reviewed", "stale": "stale (card changed)", "overdue": "overdue", "current": "current"}[c["review_state"]]])
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

    def said(m):                       # a catalogue message as one line: what (and why)
        if not m:
            return ""
        d = m.get("detail") or {}
        return " ".join(x for x in (d.get("what"), d.get("why")) if x)
    g, v, d = c["governance"] or {}, c.get("validation") or {}, c.get("data") or {}
    fid = c.get("fidelity") or {}
    x = [Paragraph(f"Model card — {c['name']}", H1), Paragraph(f"{org_name} · model-risk register · generated {datetime.now(timezone.utc).isoformat()[:16].replace('T', ' ')} UTC · card fingerprint {c['card_sha256']}", S), Spacer(1, 6),
         Paragraph("1. Identity and use", H2),
         table([["Field", "Value"], ["Hazard", c["hazard_name"]], ["Kind", c["kind_name"]], ["Model reference", c["model"]], ["Method", c["method_name"] or said(c["method_message"])],
                ["Lifecycle", c["lifecycle_name"]], ["In use", "yes" if c["active"] else "no"], ["Standing", c["standing_name"] or "—"],
                ["What it may claim", f"{c['claim']['label']}. {said(c['claim'])}"], ["Used for", said(c["use"])]], [45 * mm, 125 * mm]),
         Paragraph("2. Validation", H2),
         Paragraph(said(c["evidence"]), S),
         table([["Field", "Value"], ["Out-of-sample r²", c["r2_oos"] if c["r2_oos"] is not None else "none on record"], ["Publish gate", c["gate"]],
                ["Fidelity", f"{fid.get('family_label', '')} {fid.get('value', '—')} · {fid.get('band_label', 'not testable')}" if fid else "not testable"],
                ["Latest test", _validation_line(c)],
                ["Observed record", v.get("record") or (f"past yields, {v.get('n_years')} years, {v['baseline'][0]}–{v['baseline'][1]}" if v.get("baseline") else "—")],
                ["Second method", (f"{v['challenger']['method']} · {(c.get('validation_names') or {}).get('verdict') or v['challenger']['verdict']}" if v.get("challenger") else "none")]], [45 * mm, 125 * mm]),
         Paragraph("3. Data", H2),
         table([["Field", "Value"], ["Training data as of", d.get("training_vintage") or "—"], ["Places trained on", d.get("training_cells") or "—"],
                ["Feeds", ", ".join(f["name"] for f in c.get("feeds") or []) or "—"]] if c["kind"] == "score" else
               [["Field", "Value"], ["Crop region", d.get("region") or "—"], ["Season months", d.get("season_months") or "—"]], [45 * mm, 125 * mm]),
         Paragraph("4. What the score measures and its limits", H2)] + \
        ([Paragraph(said(c["basis"]), P)] if c.get("basis") else []) + \
        ([Paragraph(f"• {c['basis']['detail']['next']}", P)] if (c.get("basis") or {}).get("detail", {}).get("next") else []) + \
        [Paragraph(f"• {said(m)}", P) for m in c.get("limits") or []] + [
         Paragraph("5. Governance", H2),
         table([["Field", "Value"], ["Approved", f"{c['governance_names']['approved_by'] or '—'} · {(g.get('approved_at') or '')[:10]}"], ["Activated", f"{c['governance_names']['activated_by'] or '—'} · {(g.get('activated_at') or '')[:10]}"],
                ["Registered", (g.get("registered_at") or "")[:10]], ["Controls covering it", ", ".join(c.get("controls") or [])]], [45 * mm, 125 * mm])]
    if g.get("events"):
        x += [Spacer(1, 3), table([["When", "From", "To", "By", "Reason"]] + [[(e["at"] or "")[:16].replace("T", " "), w["from"] or "—", w["to"] or e["to"], w["who"], e["reason"]] for e, w in zip(g["events"], c["governance_names"]["events"])], [30 * mm, 22 * mm, 22 * mm, 30 * mm, 66 * mm])]
    x += [Paragraph("6. Independent review by the organisation", H2)]
    x += [table([["Reviewed", "Reviewer", "Conclusion", "Comment", "Next review", "Card reviewed"]] + [[(r["reviewed_at"] or "")[:10], r["reviewer"], r["conclusion_label"], r.get("comment") or "", r.get("next_review_by") or "", r["evidence_sha256"][:12]] for r in reviews],
                [22 * mm, 34 * mm, 40 * mm, 44 * mm, 20 * mm, 22 * mm])] if reviews else [Paragraph("No review recorded yet.", P)]
    doc.build(x)
    return buf.getvalue()
