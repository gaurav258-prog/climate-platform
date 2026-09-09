"""Board climate-risk pack — what the board reviews, in one immutable, hashed document, attested by name.

Assembled from the same services the screens use, for one period: the key risk indicators against the board's
appetite (green / amber / red), the breach episodes, the filing obligations and what was filed, open exceptions and
readiness, the decisions taken, what the supervisors asked and where the case file was remitted, the regulatory
changes detected, and the state of the models the figures rest on. A section the platform cannot fill says so.
Each generation is a version with its SHA-256; a board or committee member attests to that hash in a named
capacity after re-authenticating (step-up), and the attestation record prints on the pack. Nothing here names a
sector: frameworks, indicators and obligations come from the org's type through the existing registries.
"""
from __future__ import annotations

import hashlib
import io
import json
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text

SECTIONS = ["appetite", "breaches", "filings", "controls", "decisions", "supervision", "regulatory_change", "models", "method"]
STATEMENTS = {"reviewed": "I have reviewed this pack.",
              "reviewed_with_reservations": "I have reviewed this pack and record reservations (see comment)."}


def canonical_json(content: dict) -> bytes:
    return json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def sha256(content: dict) -> str:
    return hashlib.sha256(canonical_json(content)).hexdigest()


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def _last(f) -> Optional[str]:
    """reporting_requirements gives the last filing as a row; the pack keeps a readable 'period · status · date'."""
    if not f:
        return None
    if isinstance(f, dict):
        when = _iso(f.get("updated_at") or f.get("created_at")) or ""
        return f"{f.get('period_label') or ''} · {f.get('status') or ''} · {str(when)[:10]}".strip(" ·")
    return str(f)


# ── assembly ────────────────────────────────────────────────────────────────────────────────────────────────
def assemble(session, *, org: dict, actor: dict, period_from: date, period_to: date) -> dict:
    from services.governance.exception_monitor import exceptions
    from services.governance.filings import reporting_requirements
    from services.governance.kri import kri, kri_frameworks
    from services.governance.readiness import org_readiness
    from services.governance.reporting_settings import get_settings
    from services.mlops.model_governance import registry as model_registry
    from services.regulatory_monitoring.eurlex_detector import detected_changes
    from services.supervision.engagement import list_requests
    from services.supervision.remittance import list_for_entity
    org_id, org_type = org["org_id"], org.get("type")
    now = datetime.now(timezone.utc)
    st = get_settings(session, org_id)
    basis = {"scenario": st["scenario"], "horizon": st["horizon"], "reporting_period_end": _iso(st.get("reporting_period_end"))}
    c: dict = {"pack": {"title": f"Board climate-risk pack — {org['name']}", "organisation": org["name"], "sector": org_type, "period_from": period_from.isoformat(),
                        "period_to": period_to.isoformat(), "generated_at": now.isoformat(), "generated_by": actor.get("full_name") or actor.get("email"),
                        "basis": basis, "sections": SECTIONS}}

    # 1 appetite — every KRI framework for this sector, each indicator against the board's bands
    fws = [f["framework"] for f in kri_frameworks(org_type)]
    frameworks, n_red, n_amber, n_graded, n_total = [], 0, 0, 0, 0
    for fw in fws:
        try:
            k = kri(session, org_id, fw)
        except Exception as e:      # an engine that cannot evaluate says so, it does not blank the board pack
            frameworks.append({"framework": fw, "supported": False, "reason": f"could not evaluate: {type(e).__name__}"}); continue
        if not k.get("supported"):
            frameworks.append({"framework": fw, "supported": False, "reason": k.get("message")}); continue
        rows = []
        for x in k.get("kpis") or []:
            n_total += 1
            if x.get("status"):
                n_graded += 1; n_red += x["status"] == "red"; n_amber += x["status"] == "amber"
            rows.append({"key": x["key"], "label": x["label"], "value": x.get("value"), "fmt": x.get("fmt"), "status": x.get("status"),
                         "amber": x.get("amber"), "red": x.get("red"), "direction": x.get("direction"), "kind": x.get("kind"), "hint": x.get("hint")})
        frameworks.append({"framework": fw, "label": k.get("label") or fw, "supported": True, "regulator": (k.get("regulator") or {}).get("authority") if isinstance(k.get("regulator"), dict) else k.get("regulator"),
                           "kpis": rows, "breaches": k.get("breaches", 0)})
    c["appetite"] = {"frameworks": frameworks, "counts": {"indicators": n_total, "graded": n_graded, "red": n_red, "amber": n_amber},
                     "note": "Each indicator is graded against the appetite bands set in Settings → KRI appetite; an indicator without a band is shown ungraded. 'Integrated' values are brought in from outside this engine."}

    # 2 breaches — episodes open in or opened during the period
    eps = session.execute(text("""
        SELECT framework, kri_key, label, severity, direction, onset_value, peak_value, threshold, onset_at, cleared_at, acknowledged_at
        FROM kri_breach_episode WHERE org_id = CAST(:o AS uuid) AND onset_at::date <= :t AND (cleared_at IS NULL OR cleared_at::date >= :f)
        ORDER BY onset_at DESC"""), {"o": org_id, "f": period_from, "t": period_to}).mappings().all()
    c["breaches"] = {"episodes": [{**dict(r), "onset_value": float(r["onset_value"]) if r["onset_value"] is not None else None, "peak_value": float(r["peak_value"]) if r["peak_value"] is not None else None,
                                   "threshold": float(r["threshold"]) if r["threshold"] is not None else None, "onset_at": _iso(r["onset_at"]), "cleared_at": _iso(r["cleared_at"]),
                                   "acknowledged_at": _iso(r["acknowledged_at"])} for r in eps],
                     "n_open": sum(1 for r in eps if not r["cleared_at"]), "n_unacknowledged": sum(1 for r in eps if not r["acknowledged_at"] and not r["cleared_at"])}

    # 3 filings — every obligation, what was filed in the period, what is due next
    reqs = reporting_requirements(session, org_id, org_type) if org_type else []
    filed = session.execute(text("""SELECT framework, period_label, status, submission_ref, updated_at FROM regulatory_filing
                                    WHERE org_id = CAST(:o AS uuid) AND updated_at::date BETWEEN :f AND :t ORDER BY updated_at DESC"""),
                            {"o": org_id, "f": period_from, "t": period_to}).mappings().all()
    due = session.execute(text("""SELECT framework, period_label, due_date, source FROM regulatory_obligation
                                  WHERE org_id = CAST(:o AS uuid) AND due_date BETWEEN :t AND :t2 ORDER BY due_date"""),
                          {"o": org_id, "t": period_to, "t2": period_to + timedelta(days=120)}).mappings().all()
    c["filings"] = {"requirements": [{"framework": r["framework"], "label": r.get("official_name") or r.get("label"), "regulator": r.get("regulator"), "due_label": r.get("due_label"),
                                      "last_filed": _last(r.get("last_filed")), "n_filings": r.get("n_filings", 0)} for r in reqs],
                    "filed_in_period": [{**dict(r), "updated_at": _iso(r["updated_at"])} for r in filed],
                    "due_next": [{**dict(r), "due_date": _iso(r["due_date"])} for r in due],
                    "never_filed": sum(1 for r in reqs if not r.get("last_filed"))}

    # 4 controls — readiness and open exceptions
    rd = org_readiness(session, org_id, org_type)
    ex = exceptions(session, org_id)
    top = (ex.get("exceptions") or [])[:15]
    c["controls"] = {"readiness": {"passed": rd["passed"], "total": rd["total"], "failing": [{"key": x["key"], "label": x["label"], "hint": x.get("hint")} for x in rd["checks"] if not x["ok"]]},
                     "exceptions": {"open": (ex.get("summary") or {}).get("open", len(ex.get("exceptions") or [])),
                                    "top": [{"category": x.get("category"), "severity": x.get("severity"), "message": x.get("message"), "framework": x.get("framework")} for x in top]}}

    # 5 decisions taken in the period (the Signal → Decide → Act spine)
    dec = session.execute(text("""SELECT d.entity_name, d.scenario, d.horizon, d.action, d.rationale, d.status, d.decided_at, d.confirmed_at, u.full_name AS decided_by
                                  FROM risk_decision d LEFT JOIN users u ON u.user_id = d.decided_by
                                  WHERE d.org_id = CAST(:o AS uuid) AND d.decided_at::date BETWEEN :f AND :t ORDER BY d.decided_at DESC"""),
                          {"o": org_id, "f": period_from, "t": period_to}).mappings().all()
    c["decisions"] = {"n": len(dec), "n_confirmed": sum(1 for r in dec if r["confirmed_at"]),
                      "rows": [{**dict(r), "decided_at": _iso(r["decided_at"]), "confirmed_at": _iso(r["confirmed_at"])} for r in dec[:40]]}

    # 6 supervision — who supervises us, what they asked, where our case file went
    sups = session.execute(text("""SELECT o.name AS regulator, ss.jurisdiction, ss.acknowledged_at, (ss.site_access_granted_at IS NOT NULL AND ss.site_access_revoked_at IS NULL) AS site_access
                                   FROM supervision_scope ss JOIN organizations o ON o.org_id = ss.regulator_org_id WHERE ss.supervised_org_id = CAST(:o AS uuid) AND ss.active"""),
                           {"o": org_id}).mappings().all()
    reqs_s = list_requests(session, supervised_org_id=org_id)
    rem = list_for_entity(session, org_id)
    c["supervision"] = {"supervisors": [{**dict(r), "acknowledged_at": _iso(r["acknowledged_at"])} for r in sups],
                        "requests": {"n": len(reqs_s), "open": sum(1 for r in reqs_s if r["status"] != "closed"), "overdue": sum(1 for r in reqs_s if r.get("overdue")),
                                     "rows": [{"reference": r.get("reference"), "kind": r.get("kind_label") or r.get("kind"), "title": r["title"], "status": r.get("status_label") or r["status"],
                                               "due_date": r.get("due_date"), "overdue": r.get("overdue")} for r in reqs_s[:25]]},
                        "remittances": [{"reference": r["reference"], "regulator": r["regulator"], "recipient": r["recipient_name"], "kind": r["recipient_kind_label"], "purpose": r["purpose"],
                                         "status": r["status"], "expires_at": r["expires_at"], "n_downloads": r["n_downloads"]} for r in rem]}

    # 7 regulatory change — detected amendments to the frameworks this org reports under
    fw_set = {r["framework"] for r in reqs} | set(fws)
    ch = [x for x in detected_changes(session) if not fw_set or x["framework"] in fw_set]
    c["regulatory_change"] = {"n": len(ch), "rows": ch[:20], "note": "Detected from the official sources (EUR-Lex Cellar and the authorities' publications); each links to the act."}

    # 8 models — what the figures rest on
    reg = model_registry(session)
    active = [r for r in reg if r.get("is_active")]
    ev = session.execute(text("""SELECT hazard_type, from_status, to_status, actor, reason, r2_oos, created_at FROM model_status_event
                                 WHERE created_at::date BETWEEN :f AND :t ORDER BY created_at DESC"""), {"f": period_from, "t": period_to}).mappings().all()
    c["models"] = {"active": [{"hazard": r["hazard_type"], "version": r["model_version"], "algorithm": r["algorithm"], "r2_oos": float(r["r2_oos"]) if r["r2_oos"] is not None else None,
                               "status": r["lifecycle_status"], "approved_by": r["approved_by"], "activated_at": _iso(r["activated_at"])} for r in active],
                   "events_in_period": [{**dict(r), "r2_oos": float(r["r2_oos"]) if r["r2_oos"] is not None else None, "created_at": _iso(r["created_at"])} for r in ev[:30]],
                   "gate": "A model publishes a euro figure only when its out-of-sample r² is at least 0.40; below that it is a screening signal, never a number in a filing."}

    c["method"] = {"engine": "Every figure is the organisation's own engine result at the stated basis, the same result the screens and filings show; nothing is recomputed differently for the board.",
                   "appetite": "Appetite bands are the organisation's own (Settings → KRI appetite), changed only through the four-eyes approval flow.",
                   "attestation": "An attestation binds a named person, in a stated capacity, to the SHA-256 of this pack's canonical content after re-authentication (password and authenticator). It is recorded on the audit trail and printed on the pack.",
                   "honesty": "A section the platform cannot fill says so. Figures brought in from outside the engine are marked 'integrated'."}
    return c


# ── rendering ───────────────────────────────────────────────────────────────────────────────────────────────
def _fmt(v, fmt):
    if v is None:
        return "—"
    if fmt == "eur":
        v = float(v); return f"€{v/1e9:.2f}bn" if abs(v) >= 1e9 else f"€{v/1e6:.1f}m" if abs(v) >= 1e6 else f"€{v/1e3:.0f}k"
    if fmt == "pct":
        return f"{float(v):.1f}%"
    return str(v)


def render_pdf(c: dict, attestations: list[dict]) -> bytes:
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
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm, title=c["pack"]["title"], author=c["pack"]["organisation"])
    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=17, spaceAfter=4); H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12.5, spaceBefore=10, spaceAfter=4)
    P = ParagraphStyle("p", parent=ss["BodyText"], fontSize=9, leading=12); S = ParagraphStyle("s", parent=P, fontSize=7.5, textColor=colors.HexColor("#555555"))
    grid = TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7.8), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bbbbbb")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9eef5")), ("VALIGN", (0, 0), (-1, -1), "TOP")])
    TONE = {"red": "#b3261e", "amber": "#b26a00", "ok": "#1b6e3a"}

    def table(rows, widths=None, tones=None):
        cells = [[Paragraph(str("" if v is None else v), S) for v in r] for r in rows]
        t = Table(cells, colWidths=widths, repeatRows=1); t.setStyle(grid)
        for (ri, ci), tone in (tones or {}).items():
            t.setStyle(TableStyle([("TEXTCOLOR", (ci, ri), (ci, ri), colors.HexColor(TONE.get(tone, "#000000")))]))
        return t

    pk = c["pack"]; x = []
    x += [Paragraph(pk["title"], H1), Paragraph(f"Period {pk['period_from']} to {pk['period_to']} · basis {pk['basis']['scenario']} · {pk['basis']['horizon']} · generated {pk['generated_at'][:16].replace('T', ' ')} UTC by {pk['generated_by']} · content hash {pk.get('sha256', '')}", S), Spacer(1, 6)]
    a = c["appetite"]; cnt = a["counts"]
    x += [Paragraph("1. Key risk indicators against appetite", H2), Paragraph(f"{cnt['indicators']} indicators, {cnt['graded']} graded against the board's bands: {cnt['red']} red, {cnt['amber']} amber. {a['note']}", P)]
    for fw in a["frameworks"]:
        if not fw.get("supported"):
            x += [Paragraph(f"<b>{fw['framework']}</b> — {fw.get('reason') or 'not evaluated'}", P)]; continue
        rows = [["Indicator", "Value", "Status", "Amber", "Red", "Source"]]; tones = {}
        for i, k in enumerate(fw["kpis"], start=1):
            rows.append([k["label"], _fmt(k["value"], k["fmt"]), (k["status"] or "ungraded").upper(), _fmt(k["amber"], k["fmt"]), _fmt(k["red"], k["fmt"]), k["kind"]])
            if k["status"]:
                tones[(i, 2)] = k["status"]
        x += [Paragraph(f"<b>{fw['label']}</b>{(' · ' + fw['regulator']) if fw.get('regulator') else ''}", P), table(rows, [62 * mm, 24 * mm, 20 * mm, 22 * mm, 22 * mm, 22 * mm], tones)]
    b = c["breaches"]
    x += [Paragraph("2. Breach episodes in the period", H2), Paragraph(f"{len(b['episodes'])} episodes; {b['n_open']} still open, {b['n_unacknowledged']} not yet acknowledged.", P)]
    if b["episodes"]:
        x += [table([["Framework", "Indicator", "Severity", "Onset", "Peak", "Threshold", "Cleared"]] + [[e["framework"], e["label"], e["severity"], (e["onset_at"] or "")[:10], e["peak_value"], e["threshold"], (e["cleared_at"] or "open")[:10]] for e in b["episodes"]])]
    f = c["filings"]
    x += [Paragraph("3. Regulatory filings and obligations", H2), Paragraph(f"{len(f['requirements'])} mandatory frameworks, {f['never_filed']} never filed; {len(f['filed_in_period'])} filing movements in the period; {len(f['due_next'])} obligations due in the next 120 days.", P)]
    if f["requirements"]:
        x += [table([["Framework", "Authority", "Due", "Last filed", "Filings"]] + [[r["label"], r["regulator"], r["due_label"], (r["last_filed"] or "never")[:10], r["n_filings"]] for r in f["requirements"]])]
    if f["due_next"]:
        x += [Spacer(1, 4), table([["Due", "Framework", "Period", "Set by"]] + [[d["due_date"], d["framework"], d["period_label"], d["source"]] for d in f["due_next"]], [26 * mm, 50 * mm, 40 * mm, 40 * mm])]
    ct = c["controls"]
    x += [Paragraph("4. Controls: readiness and open exceptions", H2), Paragraph(f"Readiness {ct['readiness']['passed']}/{ct['readiness']['total']} checks; {ct['exceptions']['open']} open exceptions on live filings.", P)]
    if ct["readiness"]["failing"]:
        x += [table([["Failing check", "What to do"]] + [[r["label"], r.get("hint") or ""] for r in ct["readiness"]["failing"]], [70 * mm, 100 * mm])]
    if ct["exceptions"]["top"]:
        x += [Spacer(1, 4), table([["Severity", "Framework", "Category", "Finding"]] + [[e["severity"], e["framework"], e["category"], e["message"]] for e in ct["exceptions"]["top"]], [20 * mm, 30 * mm, 30 * mm, 90 * mm])]
    d = c["decisions"]
    x += [PageBreak(), Paragraph("5. Decisions taken", H2), Paragraph(f"{d['n']} decisions in the period, {d['n_confirmed']} confirmed by a second person.", P)]
    if d["rows"]:
        x += [table([["When", "Exposure", "Action", "Rationale", "Status", "By"]] + [[(r["decided_at"] or "")[:10], r["entity_name"], r["action"], r["rationale"], r["status"], r["decided_by"]] for r in d["rows"]], [20 * mm, 36 * mm, 26 * mm, 50 * mm, 18 * mm, 20 * mm])]
    sv = c["supervision"]
    x += [Paragraph("6. Supervision", H2), Paragraph(f"{len(sv['supervisors'])} supervisory bodies; {sv['requests']['n']} requests and findings ({sv['requests']['open']} open, {sv['requests']['overdue']} overdue); case file remitted onward {len(sv['remittances'])} time(s).", P)]
    if sv["supervisors"]:
        x += [table([["Authority", "Jurisdiction", "Acknowledged", "Site-level access"]] + [[s["regulator"], s["jurisdiction"], (s["acknowledged_at"] or "not yet")[:10], "granted" if s["site_access"] else "regional only"] for s in sv["supervisors"]])]
    if sv["requests"]["rows"]:
        x += [Spacer(1, 4), table([["Reference", "Kind", "Title", "Status", "Due"]] + [[r["reference"], r["kind"], r["title"], r["status"], f"{r['due_date'] or '—'}{' · overdue' if r['overdue'] else ''}"] for r in sv["requests"]["rows"]], [30 * mm, 30 * mm, 66 * mm, 24 * mm, 22 * mm])]
    if sv["remittances"]:
        x += [Spacer(1, 4), table([["Reference", "From", "To", "Purpose", "Status", "Expires"]] + [[r["reference"], r["regulator"], f"{r['recipient']} ({r['kind']})", r["purpose"], r["status"], (r["expires_at"] or "")[:10]] for r in sv["remittances"]])]
    rc = c["regulatory_change"]
    x += [Paragraph("7. Regulatory change", H2), Paragraph(f"{rc['n']} detected changes to the frameworks this organisation reports under. {rc['note']}", P)]
    if rc["rows"]:
        x += [table([["Detected", "Framework", "Title", "Effective", "Status"]] + [[r["detected_at"], r["framework"], r["title"], r["effective_date"] or "—", r["status"]] for r in rc["rows"]], [22 * mm, 26 * mm, 84 * mm, 20 * mm, 20 * mm])]
    m = c["models"]
    x += [Paragraph("8. Models the figures rest on", H2), Paragraph(f"{len(m['active'])} active models; {len(m['events_in_period'])} lifecycle events in the period. {m['gate']}", P)]
    if m["active"]:
        x += [table([["Hazard", "Version", "Algorithm", "Out-of-sample r²", "Status", "Activated"]] + [[r["hazard"], r["version"], r["algorithm"], r["r2_oos"] if r["r2_oos"] is not None else "screening", r["status"], (r["activated_at"] or "")[:10]] for r in m["active"]])]
    mt = c["method"]
    x += [Paragraph("9. Method and basis", H2)] + [Paragraph(mt[k], P) for k in ("engine", "appetite", "attestation", "honesty")]
    x += [PageBreak(), Paragraph("Attestation record", H2)]
    if attestations:
        x += [Paragraph(f"Each attestation below binds the named person to content hash {pk.get('sha256', '')} after re-authentication.", P),
              table([["Name", "Capacity", "Statement", "Comment", "When (UTC)"]] + [[at["full_name"], at["capacity"], STATEMENTS.get(at["statement"], at["statement"]), at.get("comment") or "", at["attested_at"][:16].replace("T", " ")] for at in attestations], [36 * mm, 36 * mm, 46 * mm, 30 * mm, 26 * mm])]
    else:
        x += [Paragraph("No attestation recorded yet.", P)]
    doc.build(x)
    return buf.getvalue()


# ── storage ─────────────────────────────────────────────────────────────────────────────────────────────────
def create(session, *, org: dict, actor: dict, period_from: Optional[date], period_to: Optional[date], note: Optional[str]) -> dict:
    period_to = period_to or date.today()
    period_from = period_from or (period_to - timedelta(days=90))
    if period_from >= period_to:
        raise ValueError("The period must start before it ends.")
    content = assemble(session, org=org, actor=actor, period_from=period_from, period_to=period_to)
    digest = sha256(content)
    content = {**content, "pack": {**content["pack"], "sha256": digest}}
    version = (session.execute(text("SELECT COALESCE(max(version), 0) FROM board_pack WHERE org_id = CAST(:o AS uuid)"), {"o": org["org_id"]}).scalar() or 0) + 1
    pid = session.execute(text("""INSERT INTO board_pack (org_id, version, period_from, period_to, basis, content, sha256, note, generated_by)
                                  VALUES (CAST(:o AS uuid), :v, :f, :t, CAST(:b AS jsonb), CAST(:c AS jsonb), :h, :n, CAST(:u AS uuid)) RETURNING pack_id::text"""),
                          {"o": org["org_id"], "v": version, "f": period_from, "t": period_to, "b": json.dumps(content["pack"]["basis"]), "c": canonical_json(content).decode("utf-8"),
                           "h": digest, "n": note, "u": actor.get("id")}).scalar()
    from api.services.rbac import write_audit
    write_audit(session, org_id=org["org_id"], actor_user_id=actor.get("id"), action="board_pack.generated", target_type="board_pack", target_id=pid,
                detail={"version": version, "period_from": period_from.isoformat(), "period_to": period_to.isoformat(), "sha256": digest})
    return {"pack_id": pid, "version": version, "sha256": digest, "period_from": period_from.isoformat(), "period_to": period_to.isoformat(), "summary": summary(content)}


def summary(c: dict) -> dict:
    return {"red": c["appetite"]["counts"]["red"], "amber": c["appetite"]["counts"]["amber"], "indicators": c["appetite"]["counts"]["indicators"],
            "breaches_open": c["breaches"]["n_open"], "never_filed": c["filings"]["never_filed"], "due_next": len(c["filings"]["due_next"]),
            "exceptions_open": c["controls"]["exceptions"]["open"], "readiness": f"{c['controls']['readiness']['passed']}/{c['controls']['readiness']['total']}",
            "decisions": c["decisions"]["n"], "requests_open": c["supervision"]["requests"]["open"], "reg_changes": c["regulatory_change"]["n"], "models_active": len(c["models"]["active"])}


def attestations_for(session, pack_id: str) -> list[dict]:
    rows = session.execute(text("""SELECT a.attestation_id::text AS attestation_id, u.full_name, u.email, a.capacity, a.statement, a.comment, a.sha256, a.step_up, a.ip, a.attested_at
                                   FROM board_pack_attestation a JOIN users u ON u.user_id = a.user_id WHERE a.pack_id = CAST(:p AS uuid) ORDER BY a.attested_at"""), {"p": pack_id}).mappings().all()
    return [dict(r) | {"attested_at": r["attested_at"].isoformat()} for r in rows]


def list_packs(session, org_id: str) -> list[dict]:
    rows = session.execute(text("""SELECT p.pack_id::text AS pack_id, p.version, p.period_from, p.period_to, p.basis, p.sha256, p.note, p.generated_at, u.full_name AS generated_by,
                                          (SELECT count(*) FROM board_pack_attestation a WHERE a.pack_id = p.pack_id) AS n_attestations, p.content
                                   FROM board_pack p LEFT JOIN users u ON u.user_id = p.generated_by WHERE p.org_id = CAST(:o AS uuid) ORDER BY p.version DESC"""), {"o": org_id}).mappings().all()
    out = []
    for r in rows:
        d = dict(r); c = d.pop("content")
        d["period_from"], d["period_to"], d["generated_at"] = d["period_from"].isoformat(), d["period_to"].isoformat(), d["generated_at"].isoformat()
        d["summary"] = summary(c); d["attestations"] = attestations_for(session, d["pack_id"])
        out.append(d)
    return out


def get_pack(session, org_id: str, pack_id: str) -> Optional[dict]:
    r = session.execute(text("""SELECT pack_id::text AS pack_id, version, period_from, period_to, content, sha256, generated_at FROM board_pack
                                WHERE pack_id = CAST(:p AS uuid) AND org_id = CAST(:o AS uuid)"""), {"p": pack_id, "o": org_id}).mappings().first()
    if not r:
        return None
    return dict(r) | {"period_from": r["period_from"].isoformat(), "period_to": r["period_to"].isoformat(), "generated_at": r["generated_at"].isoformat(), "attestations": attestations_for(session, pack_id)}


def attest(session, *, org_id: str, pack_id: str, actor: dict, capacity: str, statement: str, comment: Optional[str], ip: Optional[str]) -> dict:
    if statement not in STATEMENTS:
        raise ValueError(f"Statement must be one of: {', '.join(STATEMENTS)}.")
    if not (capacity or "").strip():
        raise ValueError("State the capacity in which you attest (for example 'Chair of the Risk Committee').")
    if statement == "reviewed_with_reservations" and not (comment or "").strip():
        raise ValueError("Reservations need a comment.")
    p = get_pack(session, org_id, pack_id)
    if not p:
        raise ValueError("No such board pack.")
    if any(a["email"] == actor.get("email") for a in p["attestations"]):
        raise ValueError("You have already attested this version.")
    aid = session.execute(text("""INSERT INTO board_pack_attestation (pack_id, user_id, capacity, statement, comment, sha256, step_up, ip)
                                  VALUES (CAST(:p AS uuid), CAST(:u AS uuid), :c, :s, :m, :h, TRUE, :ip) RETURNING attestation_id::text"""),
                          {"p": pack_id, "u": actor["id"], "c": capacity.strip(), "s": statement, "m": (comment or "").strip() or None, "h": p["sha256"], "ip": ip}).scalar()
    from api.services.rbac import write_audit
    write_audit(session, org_id=org_id, actor_user_id=actor["id"], action="board_pack.attested", target_type="board_pack", target_id=pack_id,
                detail={"attestation_id": aid, "version": p["version"], "sha256": p["sha256"], "capacity": capacity.strip(), "statement": statement, "step_up": True})
    return {"attestation_id": aid, "sha256": p["sha256"], "attestations": attestations_for(session, pack_id)}
