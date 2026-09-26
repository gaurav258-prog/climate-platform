"""The customer data intake pipeline — one path for every sector, every channel (file upload or API push).

    receive ─► secure ─► parse ─► map ─► check ─► stage ─┬─► import                       (every check passed — automatic)
                 │                                        ├─► awaiting_approval ─► import  (a check failed: SECOND person)
                 │                                        └─► rejected                     (nothing valid)
                 ├─► held      (no malware scanner reachable where one is required; retry later)
                 └─► rejected  (blocked by the security inspection, or infected)

Principles (agreed 2026-09-25):
  * A batch whose checks all pass is imported automatically; any failed check needs a second person — never the
    person who sent it (maker ≠ checker, via approval_requests).
  * Files are kept exactly as received (write-once) so an approved batch is imported from the SAME bytes the
    checks ran on, and every figure can be traced to its file. Files refused on security grounds are NOT kept —
    only their fingerprint and the reason.
  * Every state a batch passes through is recorded in ingest_batch_events (append-only).
  * map: the customer's own columns, units and currency → our template, by a versioned mapping profile the batch pins.
  * stage: each row is built into exactly what the engine will read and matched to the live book (new / update /
    unchanged); a re-sent book updates assets, never duplicates them (services/intake/staging.py).
"""
from __future__ import annotations

import io
import json
import re
from datetime import date, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.config import settings
from services.ingest import batch_controls as bc
from services.ingest.upload_validation import enrich_specs
from services.intake import malware, mapping, money, profiling, security, staging, storage, values
from services.intake.catalog import TEMPLATES, Template

MIN_REASON = 10


class IntakeError(Exception):
    """A refusal the caller turns into an HTTP response: status + a body the UI renders."""

    def __init__(self, status: int, body: dict):
        super().__init__(body.get("message") or body.get("error"))
        self.status, self.body = status, body


# ───────────────────────────── helpers ─────────────────────────────

def _parse(raw: bytes, detected: str, via: str) -> pd.DataFrame:
    try:
        if via == "api":
            df = pd.DataFrame(json.loads(raw.decode("utf-8")))
        elif detected == "xlsx":
            df = pd.read_excel(io.BytesIO(raw))
        else:
            df = pd.read_csv(io.BytesIO(raw), encoding_errors="replace")
    except Exception as e:  # noqa: BLE001 — any parser failure is the customer's to fix, reported plainly
        raise IntakeError(400, {"error": "unreadable", "message": f"We couldn't read the file as a table ({type(e).__name__})."})
    # column names as a person reads them: our own template marks required columns "name *"
    df.columns = [re.sub(r"\s*\*+\s*$", "", str(c)).strip() for c in df.columns]
    return df


def _missing(tpl: Template, df: pd.DataFrame) -> list[str]:
    return [s["name"] for s in tpl.specs(df) if s.get("required") and s["name"] not in df.columns]


def _required_missing(session: Session, org_id: str, tpl: Template, df: pd.DataFrame) -> Optional[dict]:
    missing = _missing(tpl, df)
    if missing:
        cols = [str(c) for c in df.columns]
        sug = profiling.suggest(session, df, enrich_specs(tpl.specs(df)))
        return {"error": "missing_columns", "missing_columns": missing, "source_columns": cols,
                "suggestion": sug, "suggested_mapping": profiling.column_map(sug),
                "closest_mapping": mapping.closest(session, org_id, tpl.key, cols),
                "message": f"The file is missing required column(s): {', '.join(missing)}. If your file names them "
                           "differently, map your columns to ours."}
    return tpl.precheck(df) if tpl.precheck else None


def _canonical(session: Session, org_id: str, tpl: Template, df: pd.DataFrame, profile_id: Optional[str],
               as_of: Optional[date] = None) -> tuple[pd.DataFrame, Optional[dict]]:
    """Apply the pinned mapping profile: the customer's columns, units and currency → our template. With none pinned,
    a file in our own layout needs none; a file in a layout the customer already confirmed uses that mapping."""
    auto = False
    if not profile_id:
        if not _missing(tpl, df):
            return df, None
        prof = mapping.for_layout(session, org_id, tpl.key, [str(c) for c in df.columns])
        if not prof:
            return df, None
        profile_id, auto = prof["profile_id"], True
    try:
        prof = mapping.get(session, org_id, profile_id)
        if prof["template"] != tpl.key:
            raise mapping.MappingError(f"That mapping is for {prof['template']}, not {tpl.key}.")
        out, rep_ = mapping.apply(session, df, prof, as_of)
        return out, {**rep_, "auto": auto}
    except mapping.MappingError as e:
        raise IntakeError(400, {"error": "mapping_failed", "message": str(e)})


def _prior_import(session: Session, org_id: str, template: str, sha: str, exclude_batch: Optional[str] = None) -> Optional[dict]:
    r = session.execute(text("""
        SELECT b.batch_id::text AS batch_id, b.state_changed_at FROM ingest_batches b
        JOIN intake_files f ON f.file_id = b.file_id
        WHERE b.org_id = CAST(:o AS uuid) AND b.template = :t AND f.sha256 = :s AND b.state = 'imported'
          AND (CAST(:x AS uuid) IS NULL OR b.batch_id <> CAST(:x AS uuid))
        ORDER BY b.state_changed_at DESC LIMIT 1
    """), {"o": org_id, "t": template, "s": sha, "x": exclude_batch}).mappings().first()
    return {"batch_id": r["batch_id"], "imported_at": str(r["state_changed_at"])[:19]} if r else None


def _money_ctx(session: Session, tpl: Template, df: pd.DataFrame, mrep: Optional[dict], currency, book_date,
               org_id: Optional[str] = None, flow_policy: Optional[str] = None) -> dict:
    try:
        ctx = money.batch_context(session, df, enrich_specs(tpl.specs(df)), mrep, currency, book_date, org_id)
        return {**ctx, "flow_policy": flow_policy} if flow_policy else ctx   # a replay keeps the policy it was checked under
    except money.MoneyError as e:
        raise IntakeError(400, {"error": "currency_declaration", "message": str(e)})


def _run_controls(session: Session, org_id: str, tpl: Template, sha: str, df: pd.DataFrame,
                  declared: Optional[dict], exclude_batch: Optional[str] = None, money_ctx: Optional[dict] = None) -> dict:
    specs = enrich_specs(tpl.specs(df))
    st = staging.stage(session, org_id, tpl.sector, df, specs, money_ctx)
    report, normalised = st["report"], st["normalised"]
    vf = tpl.value_field(df)
    vf = vf if vf in df.columns else None
    # receipt: the file as sent (declared control totals are in the file's own currency); transformation: the
    # amounts after conversion, tied to what the engine will read
    receipt = bc.receipt_check(df, declared=declared, duplicate_of=_prior_import(session, org_id, tpl.key, sha, exclude_batch))
    transform = bc.transformation_check(st["df"], specs, report, normalised, value_field=vf)
    gate = bc.evaluate_gate(receipt, transform, report["n_valid"])
    for extra in (money.gate_reason(st["money"]), values.gate_reason(st["values"]), staging.large_change_reason(st["matching"])):
        if extra and gate["status"] != "blocked":
            gate = {**gate, "status": "needs_signoff", "reasons": gate["reasons"] + [extra]}
    readiness = {"status": "pass" if not st["matching"]["n_not_ready"] else "attention",
                 "n_not_ready": st["matching"]["n_not_ready"], "value_staged": st["value_staged"]}
    return {"report": report, "normalised": normalised, "value_field": vf, "value_valid": st["value_staged"], "staged": st,
            "controls": {"receipt": receipt, "transformation": transform, "currency": st["money"], "values": st["values"],
                         "readiness": readiness,
                         "matching": {k: v for k, v in st["matching"].items()}, "gate": gate}}


def _security(raw: bytes, filename: Optional[str], tpl: Template, via: str) -> dict:
    if via == "api":   # a JSON body we parsed and re-serialised ourselves: no file format to inspect
        return {"detected_type": "json", "status": "passed", "findings": []}
    return security.inspect(raw, filename, allowed=tpl.formats)


def _malware_decision(scan: dict) -> str:
    """proceed | held | rejected — the policy on top of the scanner's answer."""
    if scan["status"] == "clean":
        return "proceed"
    if scan["status"] == "infected":
        return "rejected"
    if scan["status"] == "error":
        return "held"
    return "held" if malware.scan_required() else "proceed"   # not_configured


def _transition(session: Session, batch_id: str, org_id: str, to_state: str, *, actor_user: Optional[str] = None,
                actor_token: Optional[str] = None, detail: Optional[dict] = None, from_state: Optional[str] = None) -> None:
    session.execute(text("UPDATE ingest_batches SET state = :s, state_changed_at = now() WHERE batch_id = CAST(:b AS uuid)"),
                    {"s": to_state, "b": batch_id})
    session.execute(text("""
        INSERT INTO ingest_batch_events (batch_id, org_id, from_state, to_state, actor_user_id, actor_token_id, detail)
        VALUES (CAST(:b AS uuid), CAST(:o AS uuid), :f, :t, CAST(:u AS uuid), CAST(:k AS uuid), CAST(:d AS jsonb))
    """), {"b": batch_id, "o": org_id, "f": from_state, "t": to_state, "u": actor_user, "k": actor_token,
           "d": json.dumps(detail or {}, default=str)})


def _record_file(session: Session, org_id: str, raw: bytes, filename: Optional[str], sec: dict, scan: dict, *,
                 via: str, user_id: Optional[str], token_id: Optional[str], keep_bytes: bool) -> dict:
    import hashlib
    if keep_bytes:
        sha, uri = storage.put(raw)
    else:   # refused on security grounds: keep the fingerprint and the reason, never the content
        sha, uri = hashlib.sha256(raw).hexdigest(), "not-retained:security"
    fid = session.execute(text("""
        INSERT INTO intake_files (org_id, sha256, size_bytes, original_name, detected_type, storage_uri, received_via,
                                  received_by, token_id, security_status, security_findings, malware_status,
                                  malware_signature, malware_engine, scanned_at, retain_until)
        VALUES (CAST(:o AS uuid), :s, :n, :f, :dt, :uri, :via, CAST(:u AS uuid), CAST(:k AS uuid), :ss, CAST(:sf AS jsonb),
                :ms, :sig, :eng, CASE WHEN :ms IN ('clean', 'infected') THEN now() END, :ret)
        RETURNING file_id::text
    """), {"o": org_id, "s": sha, "n": len(raw), "f": filename, "dt": sec["detected_type"], "uri": uri, "via": via,
           "u": user_id, "k": token_id, "ss": sec["status"], "sf": json.dumps(sec["findings"]),
           "ms": scan["status"] if scan["status"] != "skipped" else "not_scanned", "sig": scan.get("signature"),
           "eng": scan.get("engine"), "ret": date.today() + timedelta(days=settings.INTAKE_RETENTION_DAYS)}).scalar()
    return {"file_id": fid, "sha256": sha}


def _new_batch(session: Session, org_id: str, tpl: Template, file: dict, filename: Optional[str], *, via: str,
               user_id: Optional[str], token_id: Optional[str], declared: Optional[dict], reason: Optional[str],
               profile_id: Optional[str] = None, money_ctx: Optional[dict] = None) -> str:
    bid = session.execute(text("""
        INSERT INTO ingest_batches (org_id, template, via, filename, sha256, received_by, token_id, file_id, declared, maker_reason,
                                    mapping_profile_id, currency, book_date, state)
        VALUES (CAST(:o AS uuid), :t, :via, :f, :s, CAST(:u AS uuid), CAST(:k AS uuid), CAST(:fid AS uuid), CAST(:d AS jsonb), :r,
                CAST(:mp AS uuid), :ccy, :bd, 'received')
        RETURNING batch_id::text
    """), {"o": org_id, "t": tpl.key, "via": via, "f": filename, "s": file["sha256"], "u": user_id, "k": token_id,
           "fid": file["file_id"], "d": json.dumps(declared or {}), "r": reason, "mp": profile_id,
           "ccy": (money_ctx or {}).get("currency"), "bd": (money_ctx or {}).get("book_date")}).scalar()
    session.execute(text("""
        INSERT INTO ingest_batch_events (batch_id, org_id, from_state, to_state, actor_user_id, actor_token_id, detail)
        VALUES (CAST(:b AS uuid), CAST(:o AS uuid), NULL, 'received', CAST(:u AS uuid), CAST(:k AS uuid), CAST(:d AS jsonb))
    """), {"b": bid, "o": org_id, "u": user_id, "k": token_id,
           "d": json.dumps({"filename": filename, "file_id": file["file_id"], "via": via})})
    return bid


def _store_controls(session: Session, batch_id: str, ctl: dict) -> None:
    r = ctl["report"]
    session.execute(text("""
        UPDATE ingest_batches SET n_total = :nt, n_valid = :nv, n_rejected = :ne, value_field = :vf, value_valid = :vv,
               receipt = CAST(:rc AS jsonb), transform = CAST(:tr AS jsonb), gate_status = :g, gate_reasons = CAST(:gr AS jsonb),
               match_summary = CAST(:ms AS jsonb), mapping_report = CAST(:mr AS jsonb), money_report = CAST(:mo AS jsonb)
        WHERE batch_id = CAST(:b AS uuid)
    """), {"mo": json.dumps(ctl["controls"].get("currency"), default=str), "ms": json.dumps(ctl["controls"]["matching"], default=str), "mr": json.dumps(ctl.get("mapping"), default=str),"nt": r["n_total"], "nv": r["n_valid"], "ne": r["n_error"], "vf": ctl["value_field"], "vv": ctl["value_valid"],
           "rc": json.dumps(ctl["controls"]["receipt"], default=str), "tr": json.dumps(ctl["controls"]["transformation"], default=str),
           "g": ctl["controls"]["gate"]["status"], "gr": json.dumps(ctl["controls"]["gate"]["reasons"]), "b": batch_id})
    staging.persist(session, batch_id, ctl["staged"])


def _dispatch_scoring(cell_coords: dict) -> dict:
    if not cell_coords:
        return {}
    try:   # never inside the request: raster reads run on the jobs layer (worker or child process)
        from services.tasks.jobs import submit
        return {"scoring": "queued", "n_cells": len(cell_coords), **submit("scoring.process_cells", cell_coords)}
    except Exception as exc:  # noqa: BLE001 — dispatch is best-effort; the rows are already stored
        return {"scoring": "deferred", "n_cells": len(cell_coords), "note": f"scoring will run when available ({type(exc).__name__})"}


def _land(session: Session, org_id: str, tpl: Template, batch_id: str, ctl: dict, *, actor_user: Optional[str],
          actor_token: Optional[str], from_state: str, detail: Optional[dict] = None) -> dict:
    res = staging.land(session, org_id, tpl.sector, ctl["staged"], batch_id)
    landing = bc.landing_check(n_valid=ctl["report"]["n_valid"], n_landed=res["n_landed"],
                               value_valid=ctl["value_valid"], value_landed=res["value_landed"])
    if res["n_landed"] == 0:
        session.execute(text("UPDATE ingest_batches SET landing = CAST(:l AS jsonb), ingest_notes = CAST(:n AS jsonb), rejected_reason = :r WHERE batch_id = CAST(:b AS uuid)"),
                        {"l": json.dumps(landing), "n": json.dumps(res["notes"], default=str), "b": batch_id,
                         "r": "Rows passed validation but none could be landed by the sector rules."})
        _transition(session, batch_id, org_id, "rejected", actor_user=actor_user, actor_token=actor_token,
                    from_state=from_state, detail={"reason": "nothing landed", "notes": res["notes"]})
        return {"n_landed": 0, "landing": landing, "notes": res["notes"], "processing": {}}
    session.execute(text("UPDATE ingest_batches SET landing = CAST(:l AS jsonb), ingest_notes = CAST(:n AS jsonb), imported_at = now() WHERE batch_id = CAST(:b AS uuid)"),
                    {"l": json.dumps(landing), "n": json.dumps(res["notes"], default=str), "b": batch_id})
    _transition(session, batch_id, org_id, "imported", actor_user=actor_user, actor_token=actor_token, from_state=from_state,
                detail={"n_landed": res["n_landed"], "value_landed": res["value_landed"], "landing": landing["status"], **(detail or {})})
    from api.services.rbac import write_audit
    write_audit(session, org_id=org_id, actor_user_id=actor_user, action=tpl.audit_action, target_type="ingest_batch",
                target_id=batch_id, detail={"n_rows": res["n_landed"], "batch_id": batch_id, "gate": ctl["controls"]["gate"]["status"]})
    return {"n_landed": res["n_landed"], "landing": landing, "notes": res["notes"], "processing": _dispatch_scoring(res["cell_coords"])}


def _owner_of_token(session: Session, token_id: str) -> Optional[str]:
    r = session.execute(text("SELECT created_by_user_id::text FROM ingest_tokens WHERE token_id = CAST(:t AS uuid)"),
                        {"t": token_id}).scalar()
    return r


# ───────────────────────────── public API ─────────────────────────────

def preview(session: Session, org_id: str, template: str, raw: bytes, filename: Optional[str],
            declared: Optional[dict] = None, via: str = "upload", mapping_profile_id: Optional[str] = None,
            currency: Optional[str] = None, book_date: Optional[str] = None) -> dict:
    """Everything the import will check, run on the file now — nothing stored, nothing written.
    (The malware scan runs on submission; the preview says whether a scanner is available.)"""
    tpl = TEMPLATES[template]
    sec = _security(raw, filename, tpl, via)
    if sec["status"] == "blocked":
        raise IntakeError(422, {"error": "security_blocked", "message": sec["findings"][0]["message"], "security": sec})
    df, mrep = _canonical(session, org_id, tpl, _parse(raw, sec["detected_type"], via), mapping_profile_id)
    err = _required_missing(session, org_id, tpl, df)
    if err:
        raise IntakeError(400, {**err, "security": sec})
    ctl = _run_controls(session, org_id, tpl, storage_sha(raw), df, declared,
                        money_ctx=_money_ctx(session, tpl, df, mrep, currency, book_date, org_id))
    ctl["mapping"] = mrep
    gate = ctl["controls"]["gate"]
    if sec["status"] == "warned":
        gate = {**gate, "status": "needs_signoff" if gate["status"] == "pass" else gate["status"],
                "reasons": gate["reasons"] + [f"Security: {f['message']}" for f in sec["findings"]]}
        ctl["controls"]["gate"] = gate
    r = ctl["report"]
    return {"filename": filename, "n_total": r["n_total"], "n_valid": r["n_valid"], "n_error": r["n_error"],
            "errors": r["errors"][:200], "security": {**sec, "malware_scan": "available" if malware.configured() else
                                                      ("required but unavailable" if malware.scan_required() else "not configured (development)")},
            "controls": ctl["controls"], "mapping": mrep}


def storage_sha(raw: bytes) -> str:
    import hashlib
    return hashlib.sha256(raw).hexdigest()


def submit(session: Session, org_id: str, template: str, raw: bytes, filename: Optional[str], *, via: str = "upload",
           user_id: Optional[str] = None, token_id: Optional[str] = None, declared: Optional[dict] = None,
           reason: Optional[str] = None, mapping_profile_id: Optional[str] = None, channel_id: Optional[str] = None,
           currency: Optional[str] = None, book_date: Optional[str] = None) -> dict:
    """Receive a batch and take it as far as the principles allow. Returns {"http_status", ...body}."""
    tpl = TEMPLATES[template]
    reason = (reason or "").strip() or None
    sec = _security(raw, filename, tpl, via)

    # 1. security inspection — refused files are recorded (fingerprint + reason), never kept
    if sec["status"] == "blocked":
        f = _record_file(session, org_id, raw, filename, sec, {"status": "skipped"}, via=via, user_id=user_id,
                         token_id=token_id, keep_bytes=False)
        bid = _new_batch(session, org_id, tpl, f, filename, via=via, user_id=user_id, token_id=token_id, declared=declared, reason=reason)
        msg = sec["findings"][0]["message"]
        session.execute(text("UPDATE ingest_batches SET rejected_reason = :r WHERE batch_id = CAST(:b AS uuid)"), {"r": msg, "b": bid})
        _transition(session, bid, org_id, "rejected", actor_user=user_id, actor_token=token_id, from_state="received",
                    detail={"stage": "security", "findings": sec["findings"]})
        raise IntakeError(422, {"error": "security_blocked", "message": msg, "batch_id": bid, "security": sec})

    # 2. malware scan
    scan = malware.scan(raw)
    decision = _malware_decision(scan)
    if decision == "rejected":
        f = _record_file(session, org_id, raw, filename, sec, scan, via=via, user_id=user_id, token_id=token_id, keep_bytes=False)
        bid = _new_batch(session, org_id, tpl, f, filename, via=via, user_id=user_id, token_id=token_id, declared=declared, reason=reason)
        msg = f"The file was flagged by the malware scanner ({scan.get('signature')}) and has been refused."
        session.execute(text("UPDATE ingest_batches SET rejected_reason = :r WHERE batch_id = CAST(:b AS uuid)"), {"r": msg, "b": bid})
        _transition(session, bid, org_id, "rejected", actor_user=user_id, actor_token=token_id, from_state="received",
                    detail={"stage": "malware", "signature": scan.get("signature"), "engine": scan.get("engine")})
        raise IntakeError(422, {"error": "malware_detected", "message": msg, "batch_id": bid})

    # 3. parse + required columns + controls, all in memory before anything is persisted
    df, mrep = _canonical(session, org_id, tpl, _parse(raw, sec["detected_type"], via), mapping_profile_id)
    err = _required_missing(session, org_id, tpl, df)
    if err:
        raise IntakeError(400, err)
    sha = storage_sha(raw)
    mctx = _money_ctx(session, tpl, df, mrep, currency, book_date, org_id)
    ctl = _run_controls(session, org_id, tpl, sha, df, declared, money_ctx=mctx) if decision == "proceed" else None
    if ctl:
        ctl["mapping"] = mrep
    if ctl and sec["status"] == "warned":
        g = ctl["controls"]["gate"]
        ctl["controls"]["gate"] = {**g, "status": "needs_signoff" if g["status"] == "pass" else g["status"],
                                   "reasons": g["reasons"] + [f"Security: {f['message']}" for f in sec["findings"]]}
    gate = ctl["controls"]["gate"]["status"] if ctl else None
    maker = user_id or (_owner_of_token(session, token_id) if token_id else None)
    if gate == "needs_signoff" and via == "upload" and (reason is None or len(reason) < MIN_REASON):
        raise IntakeError(409, {"error": "approval_reason_required", "controls": ctl["controls"],
                                "message": f"This batch failed a check, so a second person must approve it. Say why it should "
                                           f"be imported (at least {MIN_REASON} characters) and it will be sent for approval."})
    if via != "upload" and gate == "needs_signoff" and reason is None:
        reason = (f"Sent by {'an API integration' if via == 'api' else 'the drop folder'}; a check failed, so a person "
                  "must review it before it is imported.")

    # 4. persist the file and the batch
    f = _record_file(session, org_id, raw, filename, sec, scan, via=via, user_id=user_id, token_id=token_id, keep_bytes=True)
    bid = _new_batch(session, org_id, tpl, f, filename, via=via, user_id=user_id, token_id=token_id, declared=declared, reason=reason,
                     profile_id=mapping_profile_id, money_ctx=mctx)
    if channel_id:
        session.execute(text("UPDATE ingest_batches SET channel_id = CAST(:c AS uuid) WHERE batch_id = CAST(:b AS uuid)"),
                        {"c": channel_id, "b": bid})

    if decision == "held":
        why = ("the malware scanner could not be reached" if scan["status"] == "error"
               else "a malware scan is required and no scanner is configured")
        _transition(session, bid, org_id, "held", actor_user=user_id, actor_token=token_id, from_state="received",
                    detail={"stage": "malware", "scan": scan})
        return {"http_status": 202, "batch_id": bid, "state": "held",
                "message": f"Received and stored, but not processed yet: {why}. It will be processed once scanned."}

    _store_controls(session, bid, ctl)
    _transition(session, bid, org_id, "checked", actor_user=user_id, actor_token=token_id, from_state="received",
                detail={"gate": gate, "malware": scan["status"], "security": sec["status"]})
    base = {"batch_id": bid, "controls": ctl["controls"], "security": {**sec, "malware": scan["status"]},
            "n_total": ctl["report"]["n_total"], "n_valid": ctl["report"]["n_valid"], "n_error": ctl["report"]["n_error"],
            "errors": ctl["report"]["errors"][:200], "mapping": mrep}

    if gate == "blocked":
        session.execute(text("UPDATE ingest_batches SET rejected_reason = :r WHERE batch_id = CAST(:b AS uuid)"),
                        {"r": ctl["controls"]["gate"]["reasons"][0], "b": bid})
        _transition(session, bid, org_id, "rejected", actor_user=user_id, actor_token=token_id, from_state="checked",
                    detail={"stage": "gate", "reasons": ctl["controls"]["gate"]["reasons"]})
        raise IntakeError(422, {"error": "nothing_valid", "message": "None of the rows passed the checks, so nothing can be imported.", **base, "state": "rejected"})

    if gate == "needs_signoff":
        if not maker:
            raise IntakeError(409, {"error": "no_maker", "message": "This integration has no owning user, so the batch cannot be sent for approval."})
        payload = {"batch_id": bid, "template": tpl.key, "label": tpl.label, "filename": filename,
                   "n_valid": ctl["report"]["n_valid"], "n_rejected": ctl["report"]["n_error"],
                   "reasons": ctl["controls"]["gate"]["reasons"], "maker_reason": reason,
                   "matching": {k: ctl["controls"]["matching"].get(k) for k in ("new", "update", "unchanged")}}
        rid = session.execute(text("""
            INSERT INTO approval_requests (org_id, request_type, title, payload, maker_user_id)
            VALUES (CAST(:o AS uuid), 'intake.batch', :ti, CAST(:p AS jsonb), CAST(:m AS uuid)) RETURNING request_id::text
        """), {"o": org_id, "ti": f"Import {tpl.label} · {filename or 'API batch'} ({ctl['report']['n_valid']} rows)",
               "p": json.dumps(payload, default=str), "m": maker}).scalar()
        session.execute(text("UPDATE ingest_batches SET approval_request_id = CAST(:r AS uuid) WHERE batch_id = CAST(:b AS uuid)"),
                        {"r": rid, "b": bid})
        _transition(session, bid, org_id, "awaiting_approval", actor_user=user_id, actor_token=token_id, from_state="checked",
                    detail={"approval_request_id": rid, "maker": maker, "reason": reason})
        return {"http_status": 202, **base, "state": "awaiting_approval", "approval_request_id": rid,
                "message": "A check failed, so this batch has been sent for approval by a second person. Nothing is imported until then."}

    out = _land(session, org_id, tpl, bid, ctl, actor_user=user_id, actor_token=token_id, from_state="checked")
    if out["n_landed"] == 0:
        raise IntakeError(422, {"error": "nothing_landed", "message": "Rows passed the checks but none could be landed.",
                                **base, "notes": out["notes"], "state": "rejected"})
    base["controls"]["landing"] = out["landing"]
    return {"http_status": 200, **base, "state": "imported", "n_uploaded": out["n_landed"], "notes": out["notes"], **out["processing"]}


def _load_batch(session: Session, org_id: str, batch_id: str) -> dict:
    b = session.execute(text("""
        SELECT b.batch_id::text, b.template, b.via, b.filename, b.state, b.declared, b.gate_reasons, b.received_by::text,
               b.token_id::text, b.mapping_profile_id::text, b.received_at::date AS received_on, b.match_summary,
               b.currency, b.book_date, b.money_report->>'flow_policy' AS flow_policy,
               f.sha256, f.detected_type, f.security_findings, f.security_status
        FROM ingest_batches b JOIN intake_files f ON f.file_id = b.file_id
        WHERE b.org_id = CAST(:o AS uuid) AND b.batch_id = CAST(:b AS uuid)
    """), {"o": org_id, "b": batch_id}).mappings().first()
    if not b:
        raise IntakeError(404, {"error": "not_found", "message": "Batch not found."})
    return dict(b)


def _recheck(session: Session, org_id: str, tpl: Template, b: dict) -> dict:
    """Re-run every check on the stored bytes, through the SAME pinned mapping at the SAME FX date."""
    raw = storage.get(b["sha256"])   # verified byte-identical to what was received
    df, mrep = _canonical(session, org_id, tpl, _parse(raw, b["detected_type"], b["via"]), b["mapping_profile_id"], b["received_on"])
    ctl = _run_controls(session, org_id, tpl, b["sha256"], df, b["declared"] or None, exclude_batch=b["batch_id"],
                        money_ctx=_money_ctx(session, tpl, df, mrep, b["currency"], b["book_date"], org_id,
                                             b["flow_policy"]))
    ctl["mapping"] = mrep
    return ctl


def decide(session: Session, org_id: str, batch_id: str, decision: str, checker_user_id: str, reason: Optional[str]) -> dict:
    """Called from the approvals router after the maker ≠ checker check. Approve → import from the stored file,
    after re-running every check on those exact bytes (if anything changed since the request, refuse)."""
    b = _load_batch(session, org_id, batch_id)
    if b["state"] != "awaiting_approval":
        raise IntakeError(409, {"error": "not_awaiting", "message": f"This batch is {b['state']}, not awaiting approval."})
    if decision != "approved":
        session.execute(text("UPDATE ingest_batches SET rejected_reason = :r WHERE batch_id = CAST(:b AS uuid)"),
                        {"r": f"Not approved: {reason or decision}", "b": batch_id})
        _transition(session, batch_id, org_id, "rejected", actor_user=checker_user_id, from_state="awaiting_approval",
                    detail={"decision": decision, "reason": reason})
        return {"batch_id": batch_id, "state": "rejected"}
    tpl = TEMPLATES[b["template"]]
    ctl = _recheck(session, org_id, tpl, b)
    reasons = ctl["controls"]["gate"]["reasons"] + [f"Security: {f['message']}" for f in (b["security_findings"] or [])]
    then_m, now_m = b["match_summary"] or {}, ctl["controls"]["matching"]
    counts_moved = any(then_m.get(k) != now_m.get(k) for k in ("new", "update", "unchanged"))
    if sorted(reasons) != sorted(b["gate_reasons"] or []) or counts_moved:
        raise IntakeError(409, {"error": "changed_since_request",
                                "message": "The checks give a different result now than when approval was requested "
                                           "(for example, the same file has since been imported, or the assets it updates "
                                           "have changed). Ask the sender to resubmit.",
                                "then": b["gate_reasons"], "now": reasons,
                                "matching_then": {k: then_m.get(k) for k in ("new", "update", "unchanged")},
                                "matching_now": {k: now_m.get(k) for k in ("new", "update", "unchanged")}})
    staging.persist(session, batch_id, ctl["staged"])   # the staged rows now record exactly what lands
    out = _land(session, org_id, tpl, batch_id, ctl, actor_user=checker_user_id, actor_token=None, from_state="awaiting_approval",
                detail={"approved_by": checker_user_id, "approval_reason": reason})
    return {"batch_id": batch_id, "state": "imported" if out["n_landed"] else "rejected", "n_landed": out["n_landed"],
            "landing": out["landing"]}


def resume_held(session: Session, org_id: str, batch_id: str, actor_user_id: str) -> dict:
    """Retry the malware scan on a held batch; if it now passes, continue exactly as a fresh submission would."""
    b = _load_batch(session, org_id, batch_id)
    if b["state"] != "held":
        raise IntakeError(409, {"error": "not_held", "message": f"This batch is {b['state']}, not held."})
    raw = storage.get(b["sha256"])
    scan = malware.scan(raw)
    decision = _malware_decision(scan)
    session.execute(text("""UPDATE intake_files SET malware_status = :m, malware_signature = :s, malware_engine = :e,
                            scanned_at = now() WHERE sha256 = :h AND org_id = CAST(:o AS uuid)"""),
                    {"m": scan["status"], "s": scan.get("signature"), "e": scan.get("engine"), "h": b["sha256"], "o": org_id})
    if decision == "held":
        return {"batch_id": batch_id, "state": "held", "scan": scan}
    if decision == "rejected":
        _transition(session, batch_id, org_id, "rejected", actor_user=actor_user_id, from_state="held",
                    detail={"stage": "malware", "signature": scan.get("signature")})
        return {"batch_id": batch_id, "state": "rejected", "scan": scan}
    tpl = TEMPLATES[b["template"]]
    ctl = _recheck(session, org_id, tpl, b)
    _store_controls(session, batch_id, ctl)
    _transition(session, batch_id, org_id, "checked", actor_user=actor_user_id, from_state="held", detail={"malware": scan["status"]})
    if ctl["controls"]["gate"]["status"] != "pass":
        return {"batch_id": batch_id, "state": "checked", "controls": ctl["controls"],
                "message": "Scanned; a check failed — resubmit with a reason to send it for approval."}
    out = _land(session, org_id, tpl, batch_id, ctl, actor_user=actor_user_id, actor_token=None, from_state="checked")
    return {"batch_id": batch_id, "state": "imported", "n_landed": out["n_landed"], "landing": out["landing"]}
