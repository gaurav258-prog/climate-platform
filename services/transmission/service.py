"""Transmission service — prepare, send, record, receipt; the filing's own lifecycle and its submission case follow."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

from services.governance import filings as F
from services.governance.filing_export import export_filing, formats_for
from services.supervision.mandates import mandates_for, registry
from services.transmission.adapters import ADAPTERS, credentials_status


def channels_for(session, org_id: str) -> list[dict]:
    """Per framework this organisation files: the channel the mandate prescribes, whether the supervisor is on Tellumen,
    and whether the channel's credentials are configured."""
    org = session.execute(text("SELECT type FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": org_id}).mappings().first()
    on_tellumen = session.execute(text("SELECT count(*) FROM supervision_scope WHERE supervised_org_id = CAST(:o AS uuid) AND active"), {"o": org_id}).scalar() > 0
    chans = registry()["channels"]
    settings = _org_channel_settings(session, org_id)
    out = []
    for fw in F.available_frameworks(org["type"]):
        m = next((x for x in mandates_for([org["type"]]) if x["deliverable"].get("framework") == fw["framework"]), None)
        cid = (m or {}).get("deliverable", {}).get("channel_id")
        ch = chans.get(cid) if cid else None
        options = []
        if on_tellumen:
            options.append({"channel_id": "tellumen_supervisor", **chans["tellumen_supervisor"], "configured": True, "missing": [], "prescribed": False})
        if ch:
            cs = credentials_status(cid, ch, settings.get(cid))
            options.append({"channel_id": cid, **ch, "configured": cs["configured"] if ch["kind"] == "portal_upload" else True, "missing": cs["missing"], "prescribed": True})
        options.append({"channel_id": "nca_manual", **chans["nca_manual"], "configured": True, "missing": [], "prescribed": False})
        out.append({"framework": fw["framework"], "label": fw["label"], "mandate_id": (m or {}).get("id"), "formats": list(formats_for(fw["framework"])), "channels": options})
    return {"on_tellumen": on_tellumen, "frameworks": out}


def _org_channel_settings(session, org_id: str) -> dict:
    """channel_id → {key: decrypted value}: the organisation's own portal credentials, encrypted at rest."""
    from core.security.crypto import decrypt
    out: dict[str, dict] = {}
    for r in session.execute(text("SELECT channel_id, key, value_enc FROM org_channel_credential WHERE org_id = CAST(:o AS uuid)"), {"o": org_id}).all():
        out.setdefault(r[0], {})[r[1]] = decrypt(r[2])
    return out


def set_channel_credentials(session, *, org_id: str, channel_id: str, values: dict, by_user_id: str) -> dict:
    from core.security.crypto import encrypt
    ch = registry()["channels"].get(channel_id)
    if not ch:
        raise ValueError("Unknown channel.")
    allowed = set(ch.get("credentials") or [])
    for k, v in values.items():
        if k not in allowed:
            raise ValueError(f"{k} is not a credential this channel uses ({', '.join(sorted(allowed)) or 'none'}).")
        if v is None or v == "":
            session.execute(text("DELETE FROM org_channel_credential WHERE org_id = CAST(:o AS uuid) AND channel_id = :c AND key = :k"), {"o": org_id, "c": channel_id, "k": k})
        else:
            session.execute(text("""INSERT INTO org_channel_credential (org_id, channel_id, key, value_enc, updated_by, updated_at) VALUES (CAST(:o AS uuid), :c, :k, :v, CAST(:u AS uuid), now())
                                    ON CONFLICT (org_id, channel_id, key) DO UPDATE SET value_enc = EXCLUDED.value_enc, updated_by = EXCLUDED.updated_by, updated_at = now()"""),
                            {"o": org_id, "c": channel_id, "k": k, "v": encrypt(str(v)), "u": by_user_id})
    return credentials_status(channel_id, ch, _org_channel_settings(session, org_id).get(channel_id))


def create(session, *, org_id: str, filing_id: str, channel_id: str, fmt: Optional[str], by_user_id: str) -> dict:
    filing = F.get_filing(session, org_id, filing_id)
    if not filing:
        raise ValueError("Filing not found.")
    if filing["status"] not in ("attested", "submitted", "accepted"):
        raise ValueError("Only an attested filing can be transmitted — approve and attest it first.")
    chans = registry()["channels"]
    ch = chans.get(channel_id)
    if not ch:
        raise ValueError("Unknown channel.")
    fmts = [f for f in formats_for(filing["framework"]) if f in ch["formats"]] or list(formats_for(filing["framework"]))
    fmt = fmt or fmts[0]
    if fmt not in formats_for(filing["framework"]):
        raise ValueError(f"'{fmt}' is not an available format for this filing.")
    filename, media_type, payload = export_filing(session, org_id, filing_id, fmt)
    tid = session.execute(text("""
        INSERT INTO filing_transmission (org_id, filing_id, framework, period_label, channel_id, channel_kind, format, status, payload_sha256, payload_bytes, filename, created_by)
        VALUES (CAST(:o AS uuid), CAST(:f AS uuid), :fw, :pl, :c, :k, :fmt, 'queued', :sha, :n, :fn, CAST(:u AS uuid)) RETURNING transmission_id::text
    """), {"o": org_id, "f": filing_id, "fw": filing["framework"], "pl": filing["period_label"], "c": channel_id, "k": ch["kind"], "fmt": fmt,
           "sha": hashlib.sha256(payload).hexdigest(), "n": len(payload), "fn": filename, "u": by_user_id}).scalar()
    return {"transmission_id": tid, "filename": filename, "format": fmt, "channel_kind": ch["kind"]}


def _export(session, org_id, filing_id, fmt):
    return export_filing(session, org_id, filing_id, fmt)


def send(transmission_id: str) -> dict:
    """Worker entry point: run the adapter for one queued transmission and record the outcome."""
    from core.db.session import get_session
    with get_session() as s:
        t = s.execute(text("SELECT * FROM filing_transmission WHERE transmission_id = CAST(:t AS uuid)"), {"t": transmission_id}).mappings().first()
        if not t:
            return {"error": "no such transmission"}
        org_id, filing_id = str(t["org_id"]), str(t["filing_id"])
        filing = F.get_filing(s, org_id, filing_id)
        filename, _, payload = _export(s, org_id, filing_id, t["format"])
        adapter = ADAPTERS[t["channel_kind"]]
        s.execute(text("UPDATE filing_transmission SET attempts = attempts + 1, updated_at = now() WHERE transmission_id = CAST(:t AS uuid)"), {"t": transmission_id})
        try:
            res = adapter.send(s, org_id=org_id, filing=filing, payload=payload, filename=filename, fmt=t["format"], channel_id=t["channel_id"],
                               org_settings=_org_channel_settings(s, org_id).get(t["channel_id"]))
        except Exception as e:
            res = {"status": "failed", "error": f"{type(e).__name__}: {e}"}
        now = datetime.now(timezone.utc)
        s.execute(text("""UPDATE filing_transmission SET status = :st, error = :err, receipt_ref = COALESCE(:ref, receipt_ref), receipt_at = COALESCE(:rat, receipt_at),
                          receipt_payload = CAST(:rp AS jsonb), recipient_org_id = CAST(:rcp AS uuid), sent_at = CASE WHEN :st IN ('sent','acknowledged','awaiting_receipt') THEN :now ELSE sent_at END,
                          updated_at = now() WHERE transmission_id = CAST(:t AS uuid)"""),
                  {"st": res.get("status"), "err": res.get("error"), "ref": res.get("receipt_ref"), "rat": res.get("receipt_at"), "rp": json.dumps(res.get("receipt_payload") or {}, default=str),
                   "rcp": res.get("recipient_org_id"), "now": now, "t": transmission_id})
        _follow_up(s, org_id, filing, transmission_id, res, str(t["created_by"]) if t["created_by"] else None)
        s.commit()
        return {"transmission_id": transmission_id, "status": res.get("status"), "receipt_ref": res.get("receipt_ref"), "error": res.get("error")}


def _follow_up(session, org_id: str, filing: dict, transmission_id: str, res: dict, actor_user_id: Optional[str] = None) -> None:
    """The filing's lifecycle and its submission case follow the transmission outcome. Each step runs in its own
    savepoint: a failure in one is recorded on the transmission and never aborts the transmission record itself."""
    from services.governance import transmission as CASES
    st = res.get("status")
    notes = []

    def step(name, fn):
        try:
            with session.begin_nested():
                fn()
        except Exception as e:
            notes.append(f"{name}: {type(e).__name__}: {str(e)[:160]}")

    if st in ("sent", "acknowledged", "awaiting_receipt") and filing["status"] == "attested":
        step("filing.submit", lambda: F.submit(session, org_id, filing["filing_id"], actor_user_id, res.get("receipt_ref")))
        filing = F.get_filing(session, org_id, filing["filing_id"]) or filing
    if st == "acknowledged" and filing["status"] == "submitted":
        step("filing.accept", lambda: F.accept(session, org_id, filing["filing_id"], actor_user_id, res.get("receipt_ref")))

    def case_step():
        case = CASES.case_for_filing(session, org_id, filing["filing_id"])
        chans = registry()["channels"]
        ch = session.execute(text("SELECT channel_id FROM filing_transmission WHERE transmission_id = CAST(:t AS uuid)"), {"t": transmission_id}).scalar()
        if not case:
            case = CASES.open_case(session, org_id, actor_user_id, regulator=chans.get(ch, {}).get("authority", "Authority"), filing_id=filing["filing_id"], reference=res.get("receipt_ref"))
        msg = {"queued": "Transmission queued.", "sent": "Transmitted; awaiting the authority's receipt.", "acknowledged": f"Transmitted and receipted: {res.get('receipt_ref')}.",
               "awaiting_receipt": "File prepared for a channel outside the platform; record the authority's reference when received.",
               "awaiting_credentials": f"Not sent: {res.get('error')}", "rejected": f"Rejected by the authority: {res.get('error')}", "failed": f"Transmission failed: {res.get('error')}"}.get(st, st)
        CASES.post_message(session, org_id, case["case_id"], actor_user_id, direction="outbound", author="Tellumen transmission", body=msg, attachment_ref=res.get("receipt_ref"))
        if st in ("sent", "acknowledged", "awaiting_receipt") and case.get("stage") == "ready":
            CASES.advance_stage(session, org_id, case["case_id"], actor_user_id, "submitted")
    step("submission_case", case_step)
    if notes:
        session.execute(text("UPDATE filing_transmission SET error = COALESCE(error || ' · ', '') || :n WHERE transmission_id = CAST(:t AS uuid)"),
                        {"n": "follow-up: " + " | ".join(notes), "t": transmission_id})


def record_receipt(session, *, org_id: str, transmission_id: str, receipt_ref: str, by_user_id: str, note: Optional[str] = None) -> Optional[dict]:
    t = session.execute(text("SELECT filing_id::text, status FROM filing_transmission WHERE transmission_id = CAST(:t AS uuid) AND org_id = CAST(:o AS uuid)"),
                        {"t": transmission_id, "o": org_id}).mappings().first()
    if not t:
        return None
    now = datetime.now(timezone.utc)
    session.execute(text("""UPDATE filing_transmission SET status = 'acknowledged', receipt_ref = :r, receipt_at = :at, receipt_payload = CAST(:rp AS jsonb), updated_at = now()
                            WHERE transmission_id = CAST(:t AS uuid)"""), {"r": receipt_ref, "at": now, "rp": json.dumps({"recorded_by": by_user_id, "note": note}), "t": transmission_id})
    filing = F.get_filing(session, org_id, t["filing_id"])
    _follow_up(session, org_id, filing, transmission_id, {"status": "acknowledged", "receipt_ref": receipt_ref}, by_user_id)
    return {"transmission_id": transmission_id, "status": "acknowledged", "receipt_ref": receipt_ref}


def list_for_filing(session, org_id: str, filing_id: str) -> list[dict]:
    return _rows(session, "t.org_id = CAST(:o AS uuid) AND t.filing_id = CAST(:f AS uuid)", {"o": org_id, "f": filing_id})


def list_for_org(session, org_id: str) -> list[dict]:
    return _rows(session, "t.org_id = CAST(:o AS uuid)", {"o": org_id})


def received_by(session, regulator_org_id: str, supervised_org_id: Optional[str] = None) -> list[dict]:
    where = "t.recipient_org_id = CAST(:r AS uuid)" + (" AND t.org_id = CAST(:s AS uuid)" if supervised_org_id else "")
    return _rows(session, where, {"r": regulator_org_id, "s": supervised_org_id})


def _rows(session, where: str, params: dict) -> list[dict]:
    chans = registry()["channels"]
    rows = session.execute(text(f"""SELECT t.transmission_id::text AS transmission_id, t.org_id::text AS org_id, o.name AS entity, t.filing_id::text AS filing_id, t.framework, t.period_label,
                                         t.channel_id, t.channel_kind, t.format, t.status, t.attempts, t.payload_sha256, t.payload_bytes, t.filename, t.sent_at, t.receipt_ref, t.receipt_at,
                                         t.receipt_payload, t.error, t.created_at, u.full_name AS created_by
                                  FROM filing_transmission t JOIN organizations o ON o.org_id = t.org_id LEFT JOIN users u ON u.user_id = t.created_by
                                  WHERE {where} ORDER BY t.created_at DESC"""), params).mappings().all()
    # A transmission still waiting on the worker (queued, or failed and awaiting its retry) carries the worker's live
    # state, so the UI can say "worker unavailable — queued since …" instead of a bare "queued" forever.
    from services.tasks.jobs import worker_state
    ws = worker_state(_worker_status(session)) if any(r["status"] in WAITING_ON_WORKER for r in rows) else None
    return [dict(r) | {k: (r[k].isoformat() if r[k] else None) for k in ("sent_at", "receipt_at", "created_at")}
            | {"channel_label": chans.get(r["channel_id"], {}).get("label", r["channel_id"]), "worker_state": ws if r["status"] in WAITING_ON_WORKER else None}
            for r in rows]


WAITING_ON_WORKER = ("queued", "failed")


def _worker_status(session) -> dict:
    from services.tasks.jobs import worker_status
    return worker_status(session)


def worker(session) -> dict:
    """Executor liveness for the transmission responses — the same read /health exposes."""
    return _worker_status(session)
