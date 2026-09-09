"""Evidence pack — the case file a supervisor puts in front of the entity or a committee.

One immutable, versioned document per generation: everything the platform holds on the entity under this
supervisory body, assembled from the same services the screens use (nothing recomputed differently for print),
stored as canonical JSON with its SHA-256 and rendered to PDF. Every section states what it is based on; a
section the platform cannot fill says so rather than showing an empty table.
"""
from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

SECTIONS = ["identity", "supervision", "submissions", "plausibility", "lens", "projections", "exposure",
            "peer_position", "engagement", "access_trail", "method"]


def _eur(v) -> str:
    if v is None:
        return "—"
    v = float(v)
    return f"€{v/1e9:.2f}bn" if abs(v) >= 1e9 else f"€{v/1e6:.1f}m" if abs(v) >= 1e6 else f"€{v/1e3:.0f}k"


# ── assembly ────────────────────────────────────────────────────────────────────────────────────────────────
def assemble(session, *, regulator: dict, actor: dict, entity: dict, cfg: dict, scope_row: Optional[dict],
             submissions: Optional[dict], intake: Optional[dict], scenario: str, horizon: str) -> dict:
    """entity = organizations row; scope_row = the supervision_scope row (jurisdiction, since, acknowledged…);
    submissions = population row for this entity (frameworks/filed/expected); intake = sector intake spec or None."""
    from services.geo.org_assets import org_asset_points
    from services.geo.regions import aggregate_by_region
    from services.supervision.benchmark import benchmark, entity_position
    from services.supervision.engagement import get as get_request
    from services.supervision.engagement import list_requests
    from services.supervision.intake import load_submission, shadow_status
    from services.supervision.lens_build import build_lens
    from services.supervision.plausibility import assess
    from services.supervision.projection import projection_coverage, shadow_cells
    reg_id, org_id = regulator["org_id"], entity["org_id"]
    now = datetime.now(timezone.utc)
    c: dict = {"pack": {"title": f"Supervisory case file — {entity['name']}", "generated_at": now.isoformat(),
                        "generated_by": actor.get("full_name") or actor.get("email"), "regulator": regulator["name"],
                        "basis": {"scenario": scenario, "horizon": horizon}, "profile": cfg["label"], "sections": SECTIONS}}
    c["identity"] = {k: entity.get(k) for k in ("org_id", "name", "legal_name", "lei", "type", "country")}
    c["supervision"] = {"jurisdiction": (scope_row or {}).get("jurisdiction"), "since": (scope_row or {}).get("created_at"),
                        "acknowledged_at": (scope_row or {}).get("acknowledged_at"), "site_access": bool((scope_row or {}).get("site_access")),
                        "profile": cfg["label"], "sector_in_profile": entity["type"] in cfg["sectors"]}
    c["submissions"] = submissions or {"frameworks": [], "filed": 0, "expected": 0}

    sub = None
    if intake:
        ss = intake["submission"]
        sub = load_submission(session, reg_id, org_id, ss["framework"], ss["template"])
    if sub:
        basis = sub.get("basis") or {}
        sc1, hz1 = (basis.get("scenario") or scenario), (basis.get("horizon") or horizon)
        try:
            pl = assess(session, sub["cells"], sc1, hz1)
            c["plausibility"] = {"available": True, "period_label": sub.get("period_label"), "source_file": sub.get("source_file"),
                                 "scenario": sc1, "horizon": hz1, "counts": pl["counts"], "n_cells": pl["n_cells"],
                                 "coverage_value_pct": pl["coverage_value_pct"], "rule": pl["rule"],
                                 "cells": [{k: r[k] for k in ("geography", "sector", "gross_carrying_amount_eur", "submitted_share_pct", "verdict_label", "reason")}
                                           for r in pl["rows"] if r["verdict"] != "plausible"][:60]}
        except Exception as e:
            c["plausibility"] = {"available": False, "reason": f"Could not judge the template: {e}"}
    else:
        c["plausibility"] = {"available": False, "reason": "No submitted template on file for this entity under this supervisory body."}

    shadow = shadow_status(session, reg_id, org_id)["shadow_book"] if intake else {"n_rows": 0}
    if sub and shadow.get("n_rows"):
        L = build_lens(session, reg_id, org_id, sub, scenario, horizon, intake["granular"]["precision_label"])
        c["lens"] = {"available": True, "totals": L["totals"], "total_gap": L["total_gap"], "n_flagged": L["n_flagged"], "n_cells": len(L["cells"]),
                     "shadow_book": {"n_rows": shadow.get("n_rows"), "n_located": shadow.get("n_located"), "n_scored": shadow.get("n_scored")},
                     "flagged": [{k: x.get(k) for k in ("geography", "sector", "submitted_gross", "submitted_share_pct", "rebuilt_share_pct", "coverage_pct", "reason")}
                                 for x in L["cells"] if x.get("flag") == "question"][:60]}
        c["projections"] = projection_coverage(session, shadow_cells(session, reg_id, org_id))
    else:
        c["lens"] = {"available": False, "reason": "No granular data on file — the independent lens needs the supervisor's own granular rows (Tier 2)."}
        c["projections"] = {"available": False}

    pts = org_asset_points(session, org_id, scenario, horizon)
    regions = aggregate_by_region(pts)
    hz_mix: dict[str, dict] = {}
    for p in pts:
        h = hz_mix.setdefault(p["hazard"] or "unscored", {"hazard": p["hazard"] or "unscored", "n": 0, "value_eur": 0.0})
        h["n"] += 1; h["value_eur"] += float(p["value_eur"] or 0)
    c["exposure"] = {"n_assets": len(pts), "value_eur": round(sum(float(p["value_eur"] or 0) for p in pts)), "n_regions": len(regions),
                     "top_regions": [{k: r.get(k) for k in ("key", "name", "country", "kind", "n_sites", "value_eur", "max_score", "worst_hazard")} for r in regions[:10]],
                     "hazards": sorted(({**h, "value_eur": round(h["value_eur"])} for h in hz_mix.values()), key=lambda h: -h["value_eur"]),
                     "note": "Regional aggregates (NUTS-3 in the EU, land-clipped hexagons elsewhere); individual sites only where the entity granted access."}

    ents = session.execute(text("""SELECT o.org_id::text AS org_id, o.name, o.type, o.country FROM supervision_scope ss JOIN organizations o ON o.org_id = ss.supervised_org_id
                                   WHERE ss.regulator_org_id = CAST(:r AS uuid) AND ss.active"""), {"r": reg_id}).mappings().all()
    try:
        bench = benchmark(session, cfg, [dict(e) for e in ents], scenario, horizon)
        c["peer_position"] = {"peers_in_sector": bench["sectors"].get(entity["type"], {}).get("n_entities"),
                              "metrics": [{k: m.get(k) for k in ("id", "label", "unit", "value", "flag", "percentile", "distribution")} for m in entity_position(bench, org_id)]}
    except Exception as e:
        c["peer_position"] = {"metrics": [], "reason": str(e)}

    reqs = list_requests(session, regulator_org_id=reg_id, supervised_org_id=org_id)
    c["engagement"] = {"n": len(reqs), "n_open": sum(1 for r in reqs if r["status"] != "closed"),
                       "requests": [{**{k: r.get(k) for k in ("kind_label", "title", "status_label", "severity", "due_date", "raised_at", "closed_at", "overdue")},
                                     "thread": [{k: m.get(k) for k in ("side", "author", "created_at", "status_label", "body")}
                                               for m in (get_request(session, r["request_id"]) or {}).get("messages", [])]} for r in reqs]}

    trail = session.execute(text("""SELECT a.action, a.created_at, u.full_name FROM access_audit_log a LEFT JOIN users u ON u.user_id = a.actor_user_id
                                    WHERE a.org_id = CAST(:o AS uuid) AND a.action LIKE 'supervisor.%' AND (a.detail->>'regulator_org_id') = :r
                                    ORDER BY a.created_at DESC LIMIT 100"""), {"o": org_id, "r": reg_id}).mappings().all()
    c["access_trail"] = [{"action": t["action"], "at": t["created_at"].isoformat(), "by": t["full_name"]} for t in trail]
    c["method"] = {"engine": "Tellumen physical-risk engine — the same engine the entity's own workspace uses; headline hazard = max score across hazards (heat_acute excluded); sensitive = High/Very high.",
                   "tier_1": "Plausibility band: each submitted cell's sensitive share against the interquartile spread of that share across the geography's regions, from the platform's standing scores at the same basis. Location-only.",
                   "tier_2": "Independent lens: the submitted template rebuilt from the supervisor's own granular rows; gaps split into scope, coverage, basis, scoring and unmatched. A flag is a question, not a finding.",
                   "data": "Regional units: Eurostat GISCO NUTS-3 (2021) in the EU; land-clipped H3 cells elsewhere (GISCO countries 2020). No figure in this pack is estimated where data is missing — such cells say so."}
    return c


def canonical_json(content: dict) -> bytes:
    return json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def sha256(content: dict) -> str:
    return hashlib.sha256(canonical_json(content)).hexdigest()


# ── rendering ───────────────────────────────────────────────────────────────────────────────────────────────
def render_pdf(c: dict, *, sections: Optional[list[str]] = None, watermark: Optional[str] = None, notice: Optional[str] = None) -> bytes:
    """Render the pack. `sections` limits what is printed (a section outside it prints as withheld — the numbering
    stays, so the recipient can see what was not shared); `watermark` is drawn diagonally on every page and
    `notice` printed under the title. Both are used for governed remittance; the supervisor's own copy passes neither."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                            title=c["pack"]["title"], author=c["pack"]["regulator"])
    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=17, spaceAfter=4)
    H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12.5, spaceBefore=10, spaceAfter=4)
    P = ParagraphStyle("p", parent=ss["BodyText"], fontSize=9, leading=12)
    S = ParagraphStyle("s", parent=P, fontSize=7.5, textColor=colors.HexColor("#555555"))
    W = ParagraphStyle("w", parent=P, fontSize=8.5, textColor=colors.HexColor("#8a1c1c"))
    grid = TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7.8), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bbbbbb")),
                       ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9eef5")), ("VALIGN", (0, 0), (-1, -1), "TOP")])
    included = set(sections) if sections is not None else set(SECTIONS)

    def table(rows, widths=None):
        rows = [[Paragraph(str("" if v is None else v), S) for v in r] for r in rows]
        t = Table(rows, colWidths=widths, repeatRows=1); t.setStyle(grid); return t

    def withheld(title):
        return [Paragraph(title, H2), Paragraph("Withheld from this remittance.", W)]

    x = []
    pk = c["pack"]
    x += [Paragraph(pk["title"], H1), Paragraph(f"{pk['regulator']} · profile {pk['profile']} · basis {pk['basis']['scenario']} · {pk['basis']['horizon']} · "
                                                f"generated {pk['generated_at'][:16].replace('T', ' ')} UTC by {pk['generated_by']}", S)]
    if notice:
        x += [Spacer(1, 4), Paragraph(notice, W)]
    x += [Spacer(1, 6)]

    # 1 identity + supervision
    if {"identity", "supervision"} <= included:
        i, sv = c["identity"], c["supervision"]
        x += [Paragraph("1. Entity and supervision", H2),
              table([["Field", "Value"], ["Name", i["name"]], ["Legal name", i.get("legal_name")], ["LEI", i.get("lei")], ["Sector", i["type"]], ["Country", i["country"]],
                     ["Jurisdiction", sv["jurisdiction"]], ["Supervised since", (sv["since"] or "")[:10]], ["Acknowledged by the entity", (sv["acknowledged_at"] or "not yet")[:10]],
                     ["Site-level access", "granted" if sv["site_access"] else "regional aggregates only"]], [60 * mm, 110 * mm])]
    else:
        i = c["identity"]
        x += [Paragraph("1. Entity and supervision", H2), table([["Field", "Value"], ["Name", i["name"]], ["Sector", i["type"]], ["Country", i["country"]]], [60 * mm, 110 * mm]),
              Paragraph("Supervision details withheld from this remittance.", W)]
    # 2 submissions
    if "submissions" in included:
        sb = c["submissions"]
        x += [Paragraph("2. Submissions on record", H2), Paragraph(f"{sb.get('filed', 0)} of {sb.get('expected', 0)} expected framework filings on record.", P)]
        if sb.get("frameworks"):
            x += [table([["Framework", "State", "Status", "Period"]] + [[f.get("label"), f.get("state"), f.get("status"), f.get("period_label")] for f in sb["frameworks"]])]
    else:
        x += withheld("2. Submissions on record")
    # 3 plausibility
    if "plausibility" in included:
        pl = c["plausibility"]
        x += [Paragraph("3. Tier 1 — plausibility of the submitted template", H2)]
        if pl.get("available"):
            cnt = pl["counts"]
            x += [Paragraph(f"{pl['period_label']} · {pl.get('source_file') or ''} · judged at {pl['scenario']} · {pl['horizon']}. "
                            f"{cnt['plausible']} plausible, {cnt['above_band']} high for the geography, {cnt['below_band']} low, {cnt['no_reference']} without reference "
                            f"({pl['n_cells']} cells; {pl['coverage_value_pct']}% of gross amount judged).", P), Paragraph(pl["rule"], S)]
            if pl["cells"]:
                x += [table([["Cell", "Gross", "Submitted share", "Verdict", "Why"]] + [[f"{r['geography']} · {r['sector']}", _eur(r["gross_carrying_amount_eur"]),
                            f"{r['submitted_share_pct']}%" if r["submitted_share_pct"] is not None else "—", r["verdict_label"], r["reason"]] for r in pl["cells"]],
                            [22 * mm, 22 * mm, 22 * mm, 30 * mm, 74 * mm])]
        else:
            x += [Paragraph(pl.get("reason", ""), P)]
    else:
        x += withheld("3. Tier 1 — plausibility of the submitted template")
    # 4 lens (+ projections)
    if "lens" in included:
        L = c["lens"]
        x += [Paragraph("4. Tier 2 — independent lens", H2)]
        if L.get("available"):
            t = L["totals"]
            pj = c.get("projections") or {}
            x += [Paragraph(f"Submitted sensitive {_eur(t.get('submitted'))} vs rebuilt {_eur(t.get('rebuilt'))} (gap {_eur(L['total_gap'])}); {L['n_flagged']} of {L['n_cells']} cells flagged. "
                            f"Shadow book: {L['shadow_book']['n_rows']} rows, {L['shadow_book']['n_located']} located, {L['shadow_book']['n_scored']} scored. "
                            + (f"Projections: {pj.get('cells_complete', 0)}/{pj.get('cells', 0)} cells complete across {pj.get('anchors_total', 0)} anchors." if "projections" in included else "Projections withheld."), P)]
            if L["flagged"]:
                x += [table([["Cell", "Submitted gross", "Submitted share", "Rebuilt share", "Coverage", "Why it differs"]] +
                            [[f"{r['geography']} · {r['sector']}", _eur(r["submitted_gross"]), f"{r['submitted_share_pct']}%" if r["submitted_share_pct"] is not None else "—",
                              f"{r['rebuilt_share_pct']}%" if r["rebuilt_share_pct"] is not None else "—", f"{r['coverage_pct']}%" if r["coverage_pct"] is not None else "—", r["reason"]] for r in L["flagged"]],
                            [20 * mm, 22 * mm, 20 * mm, 20 * mm, 18 * mm, 70 * mm])]
        else:
            x += [Paragraph(L.get("reason", ""), P)]
    else:
        x += withheld("4. Tier 2 — independent lens")
    # 5 exposure
    if "exposure" in included:
        e = c["exposure"]
        x += [Paragraph("5. Exposure (regional)", H2), Paragraph(f"{e['n_assets']} located assets, {_eur(e['value_eur'])}, in {e['n_regions']} regions. {e['note']}", P)]
        if e["top_regions"]:
            x += [table([["Region", "Country", "Unit", "Sites", "Value", "Worst score", "Worst hazard"]] +
                        [[r["name"], r["country"], r["kind"], r["n_sites"], _eur(r["value_eur"]), r["max_score"], r["worst_hazard"]] for r in e["top_regions"]])]
        if e["hazards"]:
            x += [Spacer(1, 4), table([["Headline hazard", "Assets", "Value"]] + [[h["hazard"], h["n"], _eur(h["value_eur"])] for h in e["hazards"][:12]], [60 * mm, 30 * mm, 40 * mm])]
    else:
        x += withheld("5. Exposure (regional)")
    # 6 peer position
    if "peer_position" in included:
        pp = c["peer_position"]
        x += [Paragraph("6. Peer position", H2)]
        if pp.get("metrics"):
            x += [Paragraph(f"Against {pp.get('peers_in_sector')} peers in the sector.", P),
                  table([["Metric", "Value", "Flag", "Percentile", "Peer median"]] + [[m["label"], m["value"], m["flag"], m["percentile"], (m.get("distribution") or {}).get("median")] for m in pp["metrics"]])]
        else:
            x += [Paragraph(pp.get("reason") or "No peer benchmark for this entity's sector under the profile.", P)]
    else:
        x += withheld("6. Peer position")
    # 7 engagement
    if "engagement" in included:
        g = c["engagement"]
        x += [PageBreak(), Paragraph("7. Requests and findings", H2), Paragraph(f"{g['n']} raised, {g['n_open']} open.", P)]
        for r in g["requests"]:
            x += [Paragraph(f"<b>{r['kind_label']}</b> · {r['title']} · {r['status_label']}{(' · ' + r['severity']) if r.get('severity') else ''} · due {r.get('due_date') or '—'}"
                            f"{' · overdue' if r.get('overdue') else ''}", P)]
            if r["thread"]:
                x += [table([["Side", "By", "When", "Status", "Message"]] + [[m["side"], m["author"], (m["created_at"] or "")[:16].replace("T", " "), m.get("status_label") or "", m.get("body") or ""] for m in r["thread"]],
                            [18 * mm, 32 * mm, 26 * mm, 26 * mm, 68 * mm]), Spacer(1, 4)]
    else:
        x += withheld("7. Requests and findings")
    # 8 access trail
    if "access_trail" in included:
        x += [Paragraph("8. Supervisory access trail on this entity", H2)]
        if c["access_trail"]:
            x += [table([["When", "Action", "By"]] + [[t["at"][:16].replace("T", " "), t["action"], t["by"]] for t in c["access_trail"][:60]], [34 * mm, 80 * mm, 56 * mm])]
    else:
        x += withheld("8. Supervisory access trail on this entity")
    # 9 method
    if "method" in included:
        m = c["method"]
        x += [Paragraph("9. Method and basis", H2)] + [Paragraph(m[k], P) for k in ("engine", "tier_1", "tier_2", "data")]
    else:
        x += withheld("9. Method and basis")
    x += [Spacer(1, 8), Paragraph(f"Content hash (SHA-256 of the canonical JSON): {c['pack'].get('sha256', '')}", S)]

    def on_page(canvas, _doc):
        if not watermark:
            return
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(colors.HexColor("#8a1c1c"))
        canvas.setFillAlpha(0.35)
        w, h = A4
        canvas.translate(w / 2, h / 2)
        canvas.rotate(38)
        canvas.drawCentredString(0, 0, watermark)
        canvas.setFillAlpha(0.9)
        canvas.restoreState()
        canvas.saveState()
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(colors.HexColor("#8a1c1c"))
        canvas.drawString(18 * mm, 10 * mm, watermark)
        canvas.restoreState()

    doc.build(x, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()


# ── storage ─────────────────────────────────────────────────────────────────────────────────────────────────
def create_pack(session, *, regulator_org_id: str, supervised_org_id: str, content: dict, generated_by: str, note: Optional[str] = None) -> dict:
    digest = sha256(content)
    content = {**content, "pack": {**content["pack"], "sha256": digest}}
    pdf = render_pdf(content)
    version = (session.execute(text("""SELECT COALESCE(max(version), 0) FROM supervision_evidence_pack
                                       WHERE regulator_org_id = CAST(:r AS uuid) AND supervised_org_id = CAST(:s AS uuid)"""),
                               {"r": regulator_org_id, "s": supervised_org_id}).scalar() or 0) + 1
    pid = session.execute(text("""
        INSERT INTO supervision_evidence_pack (regulator_org_id, supervised_org_id, version, basis, content, sha256, pdf, pdf_bytes, note, generated_by)
        VALUES (CAST(:r AS uuid), CAST(:s AS uuid), :v, CAST(:b AS jsonb), CAST(:c AS jsonb), :h, :pdf, :n, :note, CAST(:u AS uuid))
        RETURNING pack_id::text
    """), {"r": regulator_org_id, "s": supervised_org_id, "v": version, "b": json.dumps(content["pack"]["basis"]),
           "c": canonical_json(content).decode("utf-8"), "h": digest, "pdf": pdf, "n": len(pdf), "note": note, "u": generated_by}).scalar()
    return {"pack_id": pid, "version": version, "sha256": digest, "pdf_bytes": len(pdf), "generated_at": content["pack"]["generated_at"]}


def list_packs(session, regulator_org_id: str, supervised_org_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT p.pack_id::text AS pack_id, p.version, p.basis, p.sha256, p.pdf_bytes, p.note, p.generated_at, u.full_name AS generated_by
        FROM supervision_evidence_pack p LEFT JOIN users u ON u.user_id = p.generated_by
        WHERE p.regulator_org_id = CAST(:r AS uuid) AND p.supervised_org_id = CAST(:s AS uuid) ORDER BY p.version DESC
    """), {"r": regulator_org_id, "s": supervised_org_id}).mappings().all()
    return [dict(r) | {"generated_at": r["generated_at"].isoformat()} for r in rows]


def get_pack(session, regulator_org_id: str, pack_id: str) -> Optional[dict]:
    r = session.execute(text("""SELECT pack_id::text AS pack_id, supervised_org_id::text AS supervised_org_id, version, content, sha256, pdf, generated_at
                                FROM supervision_evidence_pack WHERE pack_id = CAST(:p AS uuid) AND regulator_org_id = CAST(:r AS uuid)"""),
                        {"p": pack_id, "r": regulator_org_id}).mappings().first()
    return dict(r) if r else None
