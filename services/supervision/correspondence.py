"""Formal correspondence — a request or finding as the letter a regulator actually sends.

Every request carries: the authority's reference number (its own numbering, one sequence per year), the legal
basis (the mandate's article where the request arises from one, otherwise the sector's supervisory powers — both
from the registry), the response period, the signatory, and a rendered letter (PDF, hashed) that the entity can
file. The entity formally acknowledges receipt; the thread keeps everything else. Both sides hold the same
document under the same reference. Nothing here names a sector: prefixes, codes and powers are configuration.
"""
from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

from services.supervision.mandates import mandate, mandates_for, registry


def _cfg() -> dict:
    return registry()["correspondence"]


def _prefix(session, reg_org_id: str) -> str:
    row = session.execute(text("SELECT s.reference_prefix, o.name FROM organizations o LEFT JOIN supervisor_settings s ON s.org_id = o.org_id WHERE o.org_id = CAST(:o AS uuid)"),
                          {"o": reg_org_id}).first()
    if row and row[0]:
        return row[0]
    words = [w for w in (row[1] if row else "SUP").replace("(demo)", "").replace("(", " ").replace(")", " ").split() if w[0].isalpha()]
    return "".join(w[0] for w in words)[:5].upper() or "SUP"


def next_reference(session, reg_org_id: str, kind: str, when: Optional[datetime] = None) -> str:
    """Atomic per-authority, per-year sequence → e.g. EBS-2026-IR-0007."""
    when = when or datetime.now(timezone.utc)
    seq = session.execute(text("""
        INSERT INTO supervisor_reference_counter (regulator_org_id, year, next_no) VALUES (CAST(:r AS uuid), :y, 2)
        ON CONFLICT (regulator_org_id, year) DO UPDATE SET next_no = supervisor_reference_counter.next_no + 1
        RETURNING next_no - 1
    """), {"r": reg_org_id, "y": when.year}).scalar()
    return _cfg()["reference_format"].format(prefix=_prefix(session, reg_org_id), year=when.year, kind_code=_cfg()["kind_codes"].get(kind, "RQ"), seq=int(seq))


def legal_basis_for(session, reg_org_id: str, supervised_org_id: str, source: Optional[dict]) -> dict:
    """The mandate's article when the request arises from one (a deadline, a template's plausibility, a lens cell);
    otherwise the sector's supervisory powers. Always cites the act and links it."""
    from services.supervision.profiles import config_for, sector_config
    ent_type = session.execute(text("SELECT type FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": supervised_org_id}).scalar()
    m = None
    if source and source.get("mandate_id"):
        m = mandate(source["mandate_id"])
    elif source and source.get("type") in ("lens_cell", "plausibility"):
        cfg = config_for(session, reg_org_id); sec = sector_config(cfg, ent_type)
        fw = ((sec or {}).get("intake") or {}).get("submission", {}).get("framework")
        m = next((x for x in mandates_for([ent_type]) if x["deliverable"].get("framework") == fw), None)
    if m:
        return {"kind": "mandate", "mandate_id": m["id"], "ref": m["article"]["ref"], "act": m["act"]["name"], "url": m["act"]["url"], "text": m["article"]["excerpt"]}
    p = _cfg()["supervisory_powers"].get(ent_type) or {"ref": "Supervisory powers under the applicable sectoral law", "text": "", "url": None}
    return {"kind": "powers", "mandate_id": None, "ref": p["ref"], "act": p["ref"], "url": p.get("url"), "text": p.get("text", "")}


def render_letter(c: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm, topMargin=20 * mm, bottomMargin=20 * mm, title=f"{c['reference']} — {c['title']}", author=c["regulator"])
    ss = getSampleStyleSheet()
    P = ParagraphStyle("p", parent=ss["BodyText"], fontSize=10, leading=14)
    S = ParagraphStyle("s", parent=P, fontSize=8, textColor=colors.HexColor("#555555"))
    H = ParagraphStyle("h", parent=ss["Heading2"], fontSize=12.5, spaceBefore=8, spaceAfter=4)
    x = [Paragraph(c["regulator"], ParagraphStyle("org", parent=ss["Heading1"], fontSize=15)),
         Paragraph(f"Reference {c['reference']} · {c['issued_at'][:10]}", S), Spacer(1, 10),
         Paragraph(f"To: {c['entity_legal_name'] or c['entity']}{(' · LEI ' + c['entity_lei']) if c.get('entity_lei') else ''}", P), Spacer(1, 8),
         Paragraph(f"<b>Subject: {c['kind_label']} — {c['title']}</b>", P), Spacer(1, 6)]
    x += [Paragraph("Legal basis", H), Paragraph(f"{c['legal_basis']['ref']}", P)]
    if c["legal_basis"].get("text"):
        x += [Paragraph(c["legal_basis"]["text"], S)]
    if c["legal_basis"].get("url"):
        x += [Paragraph(f"<link href='{c['legal_basis']['url']}'>{c['legal_basis']['url']}</link>", S)]
    x += [Paragraph("Request", H), Paragraph((c.get("body") or "").replace("\n", "<br/>"), P)]
    if c.get("severity"):
        x += [Paragraph(f"Severity: {c['severity']}", P)]
    t = Table([["Response due", c.get("due_date") or "—"], ["Response period", f"{c['response_days']} days from issue" if c.get("response_days") else "—"],
               ["How to respond", "On the request thread in Tellumen (supervisory portal), quoting the reference."]], colWidths=[40 * mm, 120 * mm])
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bbbbbb")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    x += [Spacer(1, 6), t, Spacer(1, 14), Paragraph(c["signatory"], P), Paragraph(c["regulator"], S), Spacer(1, 10),
          Paragraph(f"Issued through Tellumen · document hash to be verified against {c.get('letter_sha256', '(assigned on issue)')}", S)]
    doc.build(x)
    return buf.getvalue()


def issue(session, request_id: str, *, regulator_org_id: str, supervised_org_id: str, kind: str, title: str, body: Optional[str],
          severity: Optional[str], due_date: Optional[str], source: Optional[dict], raised_by: Optional[str], response_days: Optional[int]) -> dict:
    """Assign the reference, legal basis, signatory and letter to a freshly created request."""
    now = datetime.now(timezone.utc)
    ref = next_reference(session, regulator_org_id, kind, now)
    basis = legal_basis_for(session, regulator_org_id, supervised_org_id, source)
    reg = session.execute(text("SELECT o.name, s.signatory_title FROM organizations o LEFT JOIN supervisor_settings s ON s.org_id = o.org_id WHERE o.org_id = CAST(:o AS uuid)"), {"o": regulator_org_id}).first()
    ent = session.execute(text("SELECT name, legal_name, lei FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": supervised_org_id}).first()
    if raised_by:
        who = session.execute(text("""SELECT u.full_name, string_agg(r.name, ', ') FROM users u LEFT JOIN user_roles ur ON ur.user_id = u.user_id
                                      LEFT JOIN roles r ON r.role_id = ur.role_id WHERE u.user_id = CAST(:u AS uuid) GROUP BY u.full_name"""), {"u": raised_by}).first()
        signatory = f"{who[0]}{(', ' + (reg[1] or who[1])) if (reg[1] or who[1]) else ''}" if who else "Supervisory staff"
    else:
        signatory = f"Issued automatically on the authority's published deadline{(' · ' + reg[1]) if reg and reg[1] else ''}"
    from services.supervision.engagement import kinds
    content = {"reference": ref, "issued_at": now.isoformat(), "regulator": reg[0] if reg else "", "entity": ent[0] if ent else "", "entity_legal_name": ent[1] if ent else None,
               "entity_lei": ent[2] if ent else None, "kind": kind, "kind_label": kinds()[kind]["label"], "title": title, "body": body, "severity": severity,
               "due_date": due_date, "response_days": response_days, "legal_basis": basis, "signatory": signatory}
    pdf = render_letter(content)
    sha = hashlib.sha256(pdf).hexdigest()
    content["letter_sha256"] = sha
    pdf = render_letter(content)      # the hash printed on the letter is the hash of the letter without it
    import json
    session.execute(text("""UPDATE supervision_request SET reference = :ref, legal_basis = CAST(:lb AS jsonb), response_days = :rd, signatory = :sg,
                            letter_pdf = :pdf, letter_sha256 = :sha, issued_at = :at WHERE request_id = CAST(:i AS uuid)"""),
                    {"ref": ref, "lb": json.dumps(basis), "rd": response_days, "sg": signatory, "pdf": pdf, "sha": sha, "at": now, "i": request_id})
    return {"reference": ref, "legal_basis": basis, "signatory": signatory, "letter_sha256": sha}


def acknowledge_receipt(session, request_id: str, supervised_org_id: str, by_user_id: str) -> bool:
    res = session.execute(text("""UPDATE supervision_request SET receipt_at = now(), receipt_by = CAST(:u AS uuid)
                                  WHERE request_id = CAST(:i AS uuid) AND supervised_org_id = CAST(:o AS uuid) AND receipt_at IS NULL"""),
                          {"u": by_user_id, "i": request_id, "o": supervised_org_id})
    return bool(res.rowcount)


def letter(session, request_id: str, *, regulator_org_id: Optional[str] = None, supervised_org_id: Optional[str] = None) -> Optional[dict]:
    r = session.execute(text("""SELECT reference, letter_pdf, letter_sha256, regulator_org_id::text AS reg, supervised_org_id::text AS ent
                                FROM supervision_request WHERE request_id = CAST(:i AS uuid)"""), {"i": request_id}).mappings().first()
    if not r or (regulator_org_id and r["reg"] != regulator_org_id) or (supervised_org_id and r["ent"] != supervised_org_id) or not r["letter_pdf"]:
        return None
    return {"reference": r["reference"], "pdf": bytes(r["letter_pdf"]), "sha256": r["letter_sha256"]}
