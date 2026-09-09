"""Governed remittance — an evidence pack shared onward to another authority, college or committee.

What the supervisor decides: who receives it (kind, name, e-mail, or a supervisory body on Tellumen), for what
purpose, on what legal basis, which sections, until when, and how many downloads. What the platform guarantees:
the remitted document is fixed at issue (scoped canonical content + watermarked PDF, both hashed), it opens only
through a bearer link whose token is shown once and stored hashed, it stops at expiry, at the download limit or
on revocation, every view and download is logged, and the supervised entity sees that its case file was
remitted — to whom, why, under which basis, until when — on its own audit trail. Nothing here names a sector:
recipient kinds, expiry limits and the watermark wording are configuration in the mandate registry.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text

from services.supervision.correspondence import legal_basis_for, next_reference
from services.supervision.evidence import SECTIONS, canonical_json, get_pack, render_pdf
from services.supervision.mandates import registry


class RemittanceError(ValueError):
    pass


def config() -> dict:
    return registry()["remittance"]


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def status_of(r: dict, now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    if r.get("revoked_at"):
        return "revoked"
    if r["expires_at"] <= now:
        return "expired"
    if r.get("max_downloads") is not None and r["n_downloads"] >= r["max_downloads"]:
        return "exhausted"
    return "active"


def scope_content(content: dict, sections: list[str], remittance: dict) -> dict:
    """The scoped canonical content: sections outside the share are replaced by an explicit withheld marker."""
    out = {"pack": dict(content["pack"]), "remittance": remittance}
    for key in SECTIONS:
        if key in sections or key == "identity":
            out[key] = content.get(key)
        else:
            out[key] = {"withheld": True, "reason": "Not included in this remittance."}
    out["pack"]["sections_included"] = list(sections)
    return out


# ── issue ───────────────────────────────────────────────────────────────────────────────────────────────────
def create(session, *, regulator_org_id: str, regulator_name: str, pack_id: str, recipient_kind: str, recipient_name: str,
           recipient_email: Optional[str], recipient_org_id: Optional[str], purpose: str, legal_basis_text: Optional[str],
           sections: Optional[list[str]], expires_in_days: Optional[int], max_downloads: Optional[int], actor: dict, link_base: str) -> dict:
    cfg = config()
    now = datetime.now(timezone.utc)
    if recipient_kind not in cfg["recipient_kinds"]:
        raise RemittanceError(f"Recipient kind must be one of: {', '.join(cfg['recipient_kinds'])}.")
    if not (recipient_name or "").strip():
        raise RemittanceError("Name the recipient.")
    if not (purpose or "").strip():
        raise RemittanceError("State the purpose of the remittance.")
    if not recipient_email and not recipient_org_id:
        raise RemittanceError("Give the recipient's e-mail, or choose a supervisory body on Tellumen.")
    days = int(expires_in_days or cfg["default_expiry_days"])
    if days < 1 or days > int(cfg["max_expiry_days"]):
        raise RemittanceError(f"Expiry must be between 1 and {cfg['max_expiry_days']} days.")
    secs = [s for s in (sections or SECTIONS) if s in SECTIONS]
    if not secs:
        raise RemittanceError("Include at least one section.")
    if max_downloads is not None and max_downloads < 1:
        raise RemittanceError("The download limit must be at least 1.")
    pack = get_pack(session, regulator_org_id, pack_id)
    if not pack:
        raise RemittanceError("No such evidence pack.")
    if recipient_org_id:
        ok = session.execute(text("SELECT 1 FROM organizations WHERE org_id = CAST(:o AS uuid) AND type = 'regulator'"), {"o": recipient_org_id}).scalar()
        if not ok:
            raise RemittanceError("The in-product recipient must be a supervisory body on Tellumen.")
        if recipient_org_id == regulator_org_id:
            raise RemittanceError("A remittance goes to another body, not to your own.")

    ref = next_reference(session, regulator_org_id, "remittance", now)
    powers = legal_basis_for(session, regulator_org_id, pack["supervised_org_id"], None)
    basis = {**powers, "stated": (legal_basis_text or "").strip() or None}
    expires = now + timedelta(days=days)
    rk_label = cfg["recipient_kinds"][recipient_kind]
    watermark = cfg["watermark_format"].format(reference=ref, regulator=regulator_name, recipient=recipient_name, expires=expires.date().isoformat())
    meta = {"reference": ref, "issued_at": now.isoformat(), "issued_by": actor.get("full_name") or actor.get("email"), "regulator": regulator_name,
            "recipient": {"kind": recipient_kind, "kind_label": rk_label, "name": recipient_name}, "purpose": purpose.strip(), "legal_basis": basis,
            "sections": secs, "expires_at": expires.isoformat(), "max_downloads": max_downloads, "notice": cfg["notice"]}
    content = scope_content(pack["content"], secs, meta)
    content_sha = hashlib.sha256(canonical_json(content)).hexdigest()
    pdf = render_pdf(content, sections=secs, watermark=watermark, notice=f"{ref} · remitted to {recipient_name} ({rk_label}) for: {purpose.strip()}. {cfg['notice']}")
    pdf_sha = hashlib.sha256(pdf).hexdigest()
    token = secrets.token_urlsafe(32)
    rid = session.execute(text("""
        INSERT INTO supervision_remittance (regulator_org_id, supervised_org_id, pack_id, reference, recipient_kind, recipient_name, recipient_org_id, recipient_email,
                                            purpose, legal_basis, sections, content, content_sha256, pdf, pdf_sha256, watermark, token_hash, expires_at, max_downloads, created_by)
        VALUES (CAST(:r AS uuid), CAST(:s AS uuid), CAST(:p AS uuid), :ref, :rk, :rn, CAST(:ro AS uuid), :re, :pu, CAST(:lb AS jsonb), CAST(:sec AS jsonb),
                CAST(:c AS jsonb), :csha, :pdf, :psha, :wm, :th, :exp, :md, CAST(:u AS uuid))
        RETURNING remittance_id::text
    """), {"r": regulator_org_id, "s": pack["supervised_org_id"], "p": pack_id, "ref": ref, "rk": recipient_kind, "rn": recipient_name.strip(), "ro": recipient_org_id,
           "re": (recipient_email or "").strip() or None, "pu": purpose.strip(), "lb": json.dumps(basis), "sec": json.dumps(secs), "c": canonical_json(content).decode("utf-8"),
           "csha": content_sha, "pdf": pdf, "psha": pdf_sha, "wm": watermark, "th": _hash(token), "exp": expires, "md": max_downloads, "u": actor.get("id")}).scalar()
    link = f"{link_base.rstrip('/')}/remit/{token}"

    from api.services.rbac import write_audit
    ent = session.execute(text("SELECT name FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": pack["supervised_org_id"]}).scalar()
    detail = {"remittance_id": rid, "reference": ref, "pack_id": pack_id, "pack_version": pack["version"], "recipient_kind": recipient_kind, "recipient": recipient_name,
              "recipient_org_id": recipient_org_id, "purpose": purpose.strip(), "legal_basis": basis["ref"], "sections": secs, "expires_at": expires.isoformat(),
              "max_downloads": max_downloads, "content_sha256": content_sha, "pdf_sha256": pdf_sha, "regulator_org_id": regulator_org_id, "regulator": regulator_name}
    for audited in (regulator_org_id, pack["supervised_org_id"]):
        write_audit(session, org_id=audited, actor_user_id=actor.get("id"), action="supervisor.evidence.remitted", target_type="supervision_remittance", target_id=rid, detail=detail)

    from services.notifications.mailer import queue_email
    body = (f"{regulator_name} has remitted a supervisory case file on {ent} to you ({rk_label}).\n\nReference: {ref}\nPurpose: {purpose.strip()}\n"
            f"Legal basis: {basis['ref']}\nSections: {', '.join(secs)}\nExpires: {expires.date().isoformat()}"
            f"{(' · at most ' + str(max_downloads) + ' downloads') if max_downloads else ''}\n\nOpen it here: {link}\n\n{cfg['notice']}")
    if recipient_email:
        queue_email(session, org_id=regulator_org_id, to_email=recipient_email, subject=f"{regulator_name}: case file on {ent} remitted · {ref}", html=None,
                    text_body=body, kind="supervision.remittance", ref_type="supervision_remittance", ref_id=rid)
    if recipient_org_id:
        from services.integrations.webhooks import emit_event
        emit_event(session, recipient_org_id, "supervision.remittance.received",
                   {"remittance_id": rid, "reference": ref, "from": regulator_name, "entity": ent, "purpose": purpose.strip(), "expires_at": expires.isoformat()})
        for em, in session.execute(text("""SELECT DISTINCT u.email FROM users u JOIN user_roles ur ON ur.user_id = u.user_id JOIN roles r ON r.role_id = ur.role_id
                                           WHERE u.org_id = CAST(:o AS uuid) AND u.status = 'active' AND r.name IN ('head', 'admin')"""), {"o": recipient_org_id}).all():
            queue_email(session, org_id=recipient_org_id, to_email=em, subject=f"{regulator_name}: case file on {ent} remitted · {ref}", html=None,
                        text_body=body + "\n\nIt is also listed under Remittances received in your Tellumen workspace.", kind="supervision.remittance",
                        ref_type="supervision_remittance", ref_id=rid)
    return {"remittance_id": rid, "reference": ref, "link": link, "expires_at": expires.isoformat(), "sections": secs, "content_sha256": content_sha,
            "pdf_sha256": pdf_sha, "watermark": watermark, "legal_basis": basis, "recipient": meta["recipient"]}


def revoke(session, *, regulator_org_id: str, remittance_id: str, actor: dict, reason: Optional[str]) -> bool:
    row = session.execute(text("""UPDATE supervision_remittance SET revoked_at = now(), revoked_by = CAST(:u AS uuid), revoke_reason = :why
                                  WHERE remittance_id = CAST(:i AS uuid) AND regulator_org_id = CAST(:r AS uuid) AND revoked_at IS NULL
                                  RETURNING supervised_org_id::text, reference, recipient_name"""),
                          {"u": actor.get("id"), "why": (reason or "").strip() or None, "i": remittance_id, "r": regulator_org_id}).first()
    if not row:
        return False
    from api.services.rbac import write_audit
    for audited in (regulator_org_id, row[0]):
        write_audit(session, org_id=audited, actor_user_id=actor.get("id"), action="supervisor.evidence.remittance_revoked", target_type="supervision_remittance",
                    target_id=remittance_id, detail={"reference": row[1], "recipient": row[2], "reason": reason, "regulator_org_id": regulator_org_id})
    return True


# ── listing ─────────────────────────────────────────────────────────────────────────────────────────────────
_COLS = """r.remittance_id::text AS remittance_id, r.regulator_org_id::text AS regulator_org_id, r.supervised_org_id::text AS supervised_org_id, r.pack_id::text AS pack_id,
           p.version AS pack_version, r.reference, r.recipient_kind, r.recipient_name, r.recipient_org_id::text AS recipient_org_id, r.recipient_email, r.purpose,
           r.legal_basis, r.sections, r.content_sha256, r.pdf_sha256, r.watermark, r.expires_at, r.max_downloads, r.n_downloads, r.created_at, r.revoked_at, r.revoke_reason,
           cu.full_name AS created_by, ru.full_name AS revoked_by, reg.name AS regulator, ent.name AS entity, rec.name AS recipient_org"""
_FROM = """FROM supervision_remittance r JOIN supervision_evidence_pack p ON p.pack_id = r.pack_id
           JOIN organizations reg ON reg.org_id = r.regulator_org_id JOIN organizations ent ON ent.org_id = r.supervised_org_id
           LEFT JOIN organizations rec ON rec.org_id = r.recipient_org_id
           LEFT JOIN users cu ON cu.user_id = r.created_by LEFT JOIN users ru ON ru.user_id = r.revoked_by"""


def _shape(r, *, for_entity: bool = False) -> dict:
    d = dict(r)
    d["status"] = status_of(d)
    d["recipient_kind_label"] = config()["recipient_kinds"].get(d["recipient_kind"], d["recipient_kind"])
    for k in ("expires_at", "created_at", "revoked_at"):
        d[k] = d[k].isoformat() if d.get(k) else None
    if for_entity:
        d.pop("recipient_email", None)
    return d


def list_for_regulator(session, regulator_org_id: str, supervised_org_id: Optional[str] = None) -> list[dict]:
    rows = session.execute(text(f"""SELECT {_COLS} {_FROM} WHERE r.regulator_org_id = CAST(:r AS uuid)
                                    AND (CAST(:s AS uuid) IS NULL OR r.supervised_org_id = CAST(:s AS uuid)) ORDER BY r.created_at DESC"""),
                           {"r": regulator_org_id, "s": supervised_org_id}).mappings().all()
    return [_shape(r) for r in rows]


def list_for_entity(session, supervised_org_id: str) -> list[dict]:
    """What the supervised entity sees: that its case file was remitted, to whom, why, under what basis, until when — never the link."""
    rows = session.execute(text(f"SELECT {_COLS} {_FROM} WHERE r.supervised_org_id = CAST(:s AS uuid) ORDER BY r.created_at DESC"), {"s": supervised_org_id}).mappings().all()
    return [_shape(r, for_entity=True) for r in rows]


def list_received(session, recipient_org_id: str) -> list[dict]:
    rows = session.execute(text(f"SELECT {_COLS} {_FROM} WHERE r.recipient_org_id = CAST(:o AS uuid) ORDER BY r.created_at DESC"), {"o": recipient_org_id}).mappings().all()
    return [_shape(r) for r in rows]


def access_log(session, regulator_org_id: str, remittance_id: str) -> list[dict]:
    rows = session.execute(text("""SELECT a.at, a.action, a.outcome, a.ip, a.user_agent, u.full_name AS actor, o.name AS actor_org
                                   FROM supervision_remittance_access a JOIN supervision_remittance r ON r.remittance_id = a.remittance_id
                                   LEFT JOIN users u ON u.user_id = a.actor_user_id LEFT JOIN organizations o ON o.org_id = a.actor_org_id
                                   WHERE a.remittance_id = CAST(:i AS uuid) AND r.regulator_org_id = CAST(:r AS uuid) ORDER BY a.at DESC"""),
                           {"i": remittance_id, "r": regulator_org_id}).mappings().all()
    return [dict(r) | {"at": r["at"].isoformat()} for r in rows]


# ── access ──────────────────────────────────────────────────────────────────────────────────────────────────
def _record(session, remittance_id: str, action: str, outcome: str, who: dict) -> None:
    session.execute(text("""INSERT INTO supervision_remittance_access (remittance_id, action, outcome, actor_user_id, actor_org_id, ip, user_agent)
                            VALUES (CAST(:i AS uuid), :a, :o, CAST(:u AS uuid), CAST(:org AS uuid), :ip, :ua)"""),
                    {"i": remittance_id, "a": action, "o": outcome, "u": who.get("user_id"), "org": who.get("org_id"), "ip": who.get("ip"), "ua": (who.get("user_agent") or "")[:300]})


def _by_token(session, token: str):
    return session.execute(text(f"SELECT {_COLS} {_FROM} WHERE r.token_hash = :h"), {"h": _hash(token)}).mappings().first()


def _by_recipient(session, remittance_id: str, recipient_org_id: str):
    return session.execute(text(f"SELECT {_COLS} {_FROM} WHERE r.remittance_id = CAST(:i AS uuid) AND r.recipient_org_id = CAST(:o AS uuid)"),
                           {"i": remittance_id, "o": recipient_org_id}).mappings().first()


def open_remittance(session, *, token: Optional[str] = None, remittance_id: Optional[str] = None, recipient_org_id: Optional[str] = None, who: dict) -> Optional[dict]:
    """View: what the recipient sees before downloading. Logged whatever the outcome; None when the token is unknown."""
    r = _by_token(session, token) if token else _by_recipient(session, remittance_id, recipient_org_id)
    if not r:
        return None
    d = _shape(r)
    _record(session, d["remittance_id"], "view", "ok" if d["status"] == "active" else d["status"], who)
    d.pop("recipient_email", None)
    d["notice"] = config()["notice"]
    return d


def download(session, *, fmt: str, token: Optional[str] = None, remittance_id: Optional[str] = None, recipient_org_id: Optional[str] = None, who: dict) -> tuple[str, Optional[bytes], dict]:
    """→ (status, bytes-or-None, meta). Counts the download only when it is served."""
    if fmt not in ("pdf", "json"):
        raise RemittanceError("Format must be pdf or json.")
    r = _by_token(session, token) if token else _by_recipient(session, remittance_id, recipient_org_id)
    if not r:
        return "unknown", None, {}
    d = _shape(r)
    action = f"download_{fmt}"
    if d["status"] != "active":
        _record(session, d["remittance_id"], action, d["status"], who)
        return d["status"], None, d
    full = session.execute(text("SELECT content, pdf FROM supervision_remittance WHERE remittance_id = CAST(:i AS uuid)"), {"i": d["remittance_id"]}).first()
    session.execute(text("UPDATE supervision_remittance SET n_downloads = n_downloads + 1 WHERE remittance_id = CAST(:i AS uuid)"), {"i": d["remittance_id"]})
    _record(session, d["remittance_id"], action, "ok", who)
    from api.services.rbac import write_audit
    for audited in (d["regulator_org_id"], d["supervised_org_id"]):
        write_audit(session, org_id=audited, actor_user_id=who.get("user_id"), action="supervisor.evidence.remittance_downloaded", target_type="supervision_remittance",
                    target_id=d["remittance_id"], detail={"reference": d["reference"], "recipient": d["recipient_name"], "format": fmt, "ip": who.get("ip"),
                                                          "download_no": d["n_downloads"] + 1, "max_downloads": d["max_downloads"]})
    data = bytes(full[1]) if fmt == "pdf" else canonical_json(full[0])
    return "ok", data, d
