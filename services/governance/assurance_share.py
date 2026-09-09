"""Governed share of an assurance pack with the auditor — the auditor's copy of the evidence bundle behind a filing,
under a bearer link that expires, counts downloads, can be revoked, and logs every access on the audit trail.

The pack itself is the one the platform already builds (build_assurance_pack): methodology, validation record,
four-eyes approvals, provenance, hashed manifest, and now the control register. This module adds only the governed
delivery: who received it, why, until when, and what they did with it.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text

DEFAULT_DAYS, MAX_DAYS = 30, 180


def _hash(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def status_of(r: dict, now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    if r.get("revoked_at"):
        return "revoked"
    if r["expires_at"] <= now:
        return "expired"
    if r.get("max_downloads") is not None and r["n_downloads"] >= r["max_downloads"]:
        return "exhausted"
    return "active"


def create(session, *, org_id: str, org_name: str, filing_id: str, recipient_name: str, recipient_email: str, purpose: str,
           expires_in_days: Optional[int], max_downloads: Optional[int], actor: dict, link_base: str) -> dict:
    if not (recipient_name or "").strip() or "@" not in (recipient_email or ""):
        raise ValueError("Name the auditor and give a valid e-mail.")
    if not (purpose or "").strip():
        raise ValueError("State the purpose of the share.")
    days = int(expires_in_days or DEFAULT_DAYS)
    if days < 1 or days > MAX_DAYS:
        raise ValueError(f"Expiry must be between 1 and {MAX_DAYS} days.")
    f = session.execute(text("SELECT framework, period_label, status FROM regulatory_filing WHERE filing_id = CAST(:f AS uuid) AND org_id = CAST(:o AS uuid)"), {"f": filing_id, "o": org_id}).mappings().first()
    if not f:
        raise ValueError("No such filing.")
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=days)
    sid = session.execute(text("""INSERT INTO assurance_share (org_id, filing_id, recipient_name, recipient_email, purpose, token_hash, expires_at, max_downloads, created_by)
                                  VALUES (CAST(:o AS uuid), CAST(:f AS uuid), :n, :e, :p, :h, :x, :m, CAST(:u AS uuid)) RETURNING share_id::text"""),
                          {"o": org_id, "f": filing_id, "n": recipient_name.strip(), "e": recipient_email.strip().lower(), "p": purpose.strip(), "h": _hash(token), "x": expires, "m": max_downloads, "u": actor.get("id")}).scalar()
    link = f"{link_base.rstrip('/')}/assurance/{token}"
    from api.services.rbac import write_audit
    write_audit(session, org_id=org_id, actor_user_id=actor.get("id"), action="assurance.shared", target_type="regulatory_filing", target_id=filing_id,
                detail={"share_id": sid, "recipient": recipient_name.strip(), "recipient_email": recipient_email.strip().lower(), "purpose": purpose.strip(), "expires_at": expires.isoformat(), "max_downloads": max_downloads})
    from services.notifications.mailer import queue_email
    queue_email(session, org_id=org_id, to_email=recipient_email.strip(), subject=f"{org_name}: assurance pack for {f['framework']} {f['period_label']}", html=None,
                text_body=(f"{org_name} has shared the assurance pack behind its {f['framework']} {f['period_label']} filing with you.\n\nPurpose: {purpose.strip()}\n"
                           f"Expires: {expires.date().isoformat()}{(' · at most ' + str(max_downloads) + ' downloads') if max_downloads else ''}\n\nOpen it here: {link}\n\n"
                           "The pack carries the methodology, the validation record, the four-eyes approvals, the provenance, the control register and a hashed manifest. Every access is logged."),
                kind="assurance.share", ref_type="assurance_share", ref_id=sid)
    return {"share_id": sid, "link": link, "expires_at": expires.isoformat(), "framework": f["framework"], "period_label": f["period_label"]}


def revoke(session, *, org_id: str, share_id: str, actor: dict) -> bool:
    row = session.execute(text("UPDATE assurance_share SET revoked_at = now(), revoked_by = CAST(:u AS uuid) WHERE share_id = CAST(:s AS uuid) AND org_id = CAST(:o AS uuid) AND revoked_at IS NULL RETURNING filing_id::text, recipient_name"),
                          {"u": actor.get("id"), "s": share_id, "o": org_id}).first()
    if not row:
        return False
    from api.services.rbac import write_audit
    write_audit(session, org_id=org_id, actor_user_id=actor.get("id"), action="assurance.share_revoked", target_type="regulatory_filing", target_id=row[0], detail={"share_id": share_id, "recipient": row[1]})
    return True


_COLS = """s.share_id::text AS share_id, s.org_id::text AS org_id, s.filing_id::text AS filing_id, f.framework, f.period_label, s.recipient_name, s.recipient_email, s.purpose,
           s.expires_at, s.max_downloads, s.n_downloads, s.created_at, s.revoked_at, u.full_name AS created_by, o.name AS organisation"""
_FROM = "FROM assurance_share s JOIN regulatory_filing f ON f.filing_id = s.filing_id JOIN organizations o ON o.org_id = s.org_id LEFT JOIN users u ON u.user_id = s.created_by"


def _shape(r) -> dict:
    d = dict(r); d["status"] = status_of(d)
    for k in ("expires_at", "created_at", "revoked_at"):
        d[k] = d[k].isoformat() if d.get(k) else None
    return d


def list_for_filing(session, org_id: str, filing_id: str) -> list[dict]:
    rows = session.execute(text(f"SELECT {_COLS} {_FROM} WHERE s.org_id = CAST(:o AS uuid) AND s.filing_id = CAST(:f AS uuid) ORDER BY s.created_at DESC"), {"o": org_id, "f": filing_id}).mappings().all()
    out = []
    for r in rows:
        d = _shape(r)
        d["accesses"] = [dict(a) | {"at": a["at"].isoformat()} for a in session.execute(text("SELECT at, action, outcome, ip FROM assurance_share_access WHERE share_id = CAST(:s AS uuid) ORDER BY at DESC LIMIT 50"), {"s": d["share_id"]}).mappings().all()]
        out.append(d)
    return out


def _record(session, share_id: str, action: str, outcome: str, who: dict) -> None:
    session.execute(text("INSERT INTO assurance_share_access (share_id, action, outcome, ip, user_agent) VALUES (CAST(:s AS uuid), :a, :o, :ip, :ua)"),
                    {"s": share_id, "a": action, "o": outcome, "ip": who.get("ip"), "ua": (who.get("user_agent") or "")[:300]})


def open_share(session, token: str, who: dict) -> Optional[dict]:
    r = session.execute(text(f"SELECT {_COLS} {_FROM} WHERE s.token_hash = :h"), {"h": _hash(token)}).mappings().first()
    if not r:
        return None
    d = _shape(r)
    _record(session, d["share_id"], "view", "ok" if d["status"] == "active" else d["status"], who)
    d.pop("recipient_email", None)
    return d


def download(session, token: str, who: dict) -> tuple[str, Optional[tuple[str, bytes]], dict]:
    r = session.execute(text(f"SELECT {_COLS} {_FROM} WHERE s.token_hash = :h"), {"h": _hash(token)}).mappings().first()
    if not r:
        return "unknown", None, {}
    d = _shape(r)
    if d["status"] != "active":
        _record(session, d["share_id"], "download", d["status"], who)
        return d["status"], None, d
    from services.governance.assurance_pack import build_assurance_pack
    snap = session.execute(text("SELECT snapshot_id::text FROM regulatory_filing WHERE filing_id = CAST(:f AS uuid)"), {"f": d["filing_id"]}).scalar()
    built = build_assurance_pack(session, d["org_id"], snap) if snap else None
    if not built:
        _record(session, d["share_id"], "download", "unavailable", who)
        return "unavailable", None, d
    session.execute(text("UPDATE assurance_share SET n_downloads = n_downloads + 1 WHERE share_id = CAST(:s AS uuid)"), {"s": d["share_id"]})
    _record(session, d["share_id"], "download", "ok", who)
    from api.services.rbac import write_audit
    write_audit(session, org_id=d["org_id"], actor_user_id=None, action="assurance.share_downloaded", target_type="regulatory_filing", target_id=d["filing_id"],
                detail={"share_id": d["share_id"], "recipient": d["recipient_name"], "ip": who.get("ip"), "download_no": d["n_downloads"] + 1})
    return "ok", built, d
