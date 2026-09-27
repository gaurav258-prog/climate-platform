"""The manager's EET answers, and EET versions: prepare → a second person approves → published → sent.

  answers     what Tellumen can't compute, checked against the field's format. Manufacturer fields (codes below 20000)
              are answered once for the organisation; product fields per fund. A field Tellumen computes can't be
              answered (the figure comes from the book). Blank = remove the answer. Every change is audited.
  prepare     builds the EET for the active share classes and the chosen uses and freezes it as the next version
              (payload + completeness + sha256, append-only). It is refused while any mandatory field is empty.
              It raises an 'eet.publish' request: a different person must approve (4-eyes, approvals router).
  decide      approved → published (the version distributors receive); rejected / returned → rejected.
  export      renders a version — the EXACT frozen rows — as the EET file (xlsx or csv): one row per ISIN, every field
              in FinDatEx order. Only a published version is the EET; a pending one downloads as a marked draft.
  changes     compares a fresh build with the latest published version: new or changed figures mean it's time to
              prepare the next version (e.g. new holdings, a filed SFDR statement, a new share class).
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.eet import fields as F
from services.eet.generator import build, computed_names

VOLATILE = {"00050_EET_File_Generation_Date_And_Time"}


class EETError(ValueError):
    pass


# ───────────────────────────── answers ─────────────────────────────

def answers(session: Session, org_id: str, fund_id: Optional[str] = None) -> dict:
    org = {r[0]: {"value": r[1], "updated_at": r[2].isoformat()} for r in session.execute(text(
        "SELECT field_name, value, updated_at FROM org_eet_answers WHERE org_id = CAST(:o AS uuid)"), {"o": org_id})}
    fund = {}
    if fund_id:
        fund = {r[0]: {"value": r[1], "updated_at": r[2].isoformat()} for r in session.execute(text(
            "SELECT field_name, value, updated_at FROM fund_eet_answers WHERE fund_id = CAST(:f AS uuid)"), {"f": fund_id})}
    return {"organisation": org, "fund": fund}


def _scope(name: str) -> str:
    return "organisation" if int(name.split("_", 1)[0]) < 20000 else "fund"


def set_answers(session: Session, org_id: str, fund_id: Optional[str], values: dict, user_id: Optional[str]) -> dict:
    """values: {field_name: value | None}. Returns {saved, removed, refused: [{field, reason}]}."""
    if fund_id and not session.execute(text("SELECT 1 FROM funds WHERE fund_id = CAST(:f AS uuid) AND org_id = CAST(:o AS uuid)"),
                                       {"f": fund_id, "o": org_id}).first():
        raise EETError("fund not found")
    computed = computed_names()
    saved, removed, refused = [], [], []
    for name, raw in (values or {}).items():
        if name not in F.by_name():
            refused.append({"field": name, "reason": f"not an EET {F.version()} field"})
            continue
        if name in computed:
            refused.append({"field": name, "reason": "Tellumen fills this from your book — it can't be typed in"})
            continue
        scope = _scope(name)
        if scope == "fund" and not fund_id:
            refused.append({"field": name, "reason": "a product field — answer it for a fund"})
            continue
        table, key, kid = (("org_eet_answers", "org_id", org_id) if scope == "organisation"
                           else ("fund_eet_answers", "fund_id", fund_id))
        if raw is None or str(raw).strip() == "":
            n = session.execute(text(f"DELETE FROM {table} WHERE {key} = CAST(:k AS uuid) AND field_name = :n"),
                                {"k": kid, "n": name}).rowcount
            if n:
                removed.append(name)
            continue
        try:
            v = F.check(name, raw)
        except F.EETValueError as e:
            refused.append({"field": name, "reason": str(e)})
            continue
        session.execute(text(f"""
            INSERT INTO {table} ({key}, field_name, value, updated_by) VALUES (CAST(:k AS uuid), :n, :v, CAST(:u AS uuid))
            ON CONFLICT ({key}, field_name) DO UPDATE SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by, updated_at = now()
        """), {"k": kid, "n": name, "v": v, "u": user_id})
        saved.append({"field": name, "value": v, "scope": scope})
    return {"saved": saved, "removed": removed, "refused": refused}


# ───────────────────────────── versions ─────────────────────────────

def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _comparable(rows: list[dict]) -> dict:
    return {r["isin"]: {k: v for k, v in r["values"].items() if k not in VOLATILE} for r in rows}


def prepare(session: Session, org_id: str, user_id: Optional[str], uses: list[str], note: Optional[str] = None) -> dict:
    bad = [u for u in uses if u not in F.USES]
    if bad or not uses:
        raise EETError(f"choose the uses the file is for: {', '.join(F.USES)}")
    out = build(session, org_id, tuple(uses))
    comp = out["completeness"]
    if not out["rows"]:
        raise EETError("no active share classes — register the share classes the EET is for first")
    if not comp["ready"]:
        eg = ", ".join(b["field"] for b in comp["blocking"][:5])
        raise EETError(f"{comp['n_blocking']} mandatory field(s) are still empty ({eg}{', …' if comp['n_blocking'] > 5 else ''}) — "
                       f"answer them before preparing a version")
    payload = {k: out[k] for k in ("eet_version", "uses", "generated_at", "field_names", "rows", "funds", "notes")}
    sha = hashlib.sha256(_canonical(payload).encode()).hexdigest()
    version = session.execute(text("SELECT COALESCE(MAX(version), 0) + 1 FROM eet_publications WHERE org_id = CAST(:o AS uuid)"),
                              {"o": org_id}).scalar()
    ref = max((r["values"].get("10040_General_Reference_Date") or "" for r in out["rows"]), default="") or date.today().isoformat()
    pid = session.execute(text("""
        INSERT INTO eet_publications (org_id, version, eet_version, uses, reference_date, payload, completeness,
                                      payload_sha256, prepared_by)
        VALUES (CAST(:o AS uuid), :v, :ev, CAST(:u AS jsonb), :d, CAST(:p AS jsonb), CAST(:c AS jsonb), :h, CAST(:by AS uuid))
        RETURNING publication_id::text
    """), {"o": org_id, "v": version, "ev": out["eet_version"], "u": json.dumps(out["uses"]), "d": ref[:10],
           "p": _canonical(payload), "c": json.dumps(comp), "h": sha, "by": user_id}).scalar()
    rid = session.execute(text("""
        INSERT INTO approval_requests (org_id, request_type, title, payload, maker_user_id)
        VALUES (CAST(:o AS uuid), 'eet.publish', :t, CAST(:p AS jsonb), CAST(:m AS uuid)) RETURNING request_id::text
    """), {"o": org_id, "t": f"Publish EET v{version} · {len(out['rows'])} share class(es) · {', '.join(F.USE_LABEL[u] for u in out['uses'])}",
           "p": json.dumps({"publication_id": pid, "version": version, "payload_sha256": sha, "note": note}), "m": user_id}).scalar()
    session.execute(text("UPDATE eet_publications SET approval_request_id = CAST(:r AS uuid) WHERE publication_id = CAST(:p AS uuid)"),
                    {"r": rid, "p": pid})
    return get(session, org_id, pid, with_payload=False)


def apply_decision(session: Session, org_id: str, payload: dict, decision: str, actor: str, reason: Optional[str] = None) -> dict:
    """Called by the approvals router (checker ≠ maker already enforced there)."""
    pid = (payload or {}).get("publication_id")
    status = "published" if decision == "approved" else "rejected"
    n = session.execute(text("""
        UPDATE eet_publications SET status = :s, decided_by = CAST(:u AS uuid), decided_at = now(), decision_reason = :r
        WHERE publication_id = CAST(:p AS uuid) AND org_id = CAST(:o AS uuid) AND status = 'pending'
    """), {"s": status, "u": actor, "r": reason, "p": pid, "o": org_id}).rowcount
    if not n:
        raise EETError("that EET version is not awaiting a decision")
    return {"publication_id": pid, "status": status}


def _row(r, with_payload: bool) -> dict:
    out = {"publication_id": r["publication_id"], "version": r["version"], "eet_version": r["eet_version"],
           "uses": r["uses"], "reference_date": r["reference_date"].isoformat(), "status": r["status"],
           "payload_sha256": r["payload_sha256"], "prepared_by": r["prepared_by_name"], "prepared_at": r["prepared_at"].isoformat(),
           "decided_by": r["decided_by_name"], "decided_at": r["decided_at"].isoformat() if r["decided_at"] else None,
           "decision_reason": r["decision_reason"], "approval_request_id": r["approval_request_id"],
           "n_share_classes": len((r["payload"] or {}).get("rows") or []), "completeness": r["completeness"]}
    if with_payload:
        out["payload"] = r["payload"]
        out["hash_verified"] = hashlib.sha256(_canonical(r["payload"]).encode()).hexdigest() == r["payload_sha256"]
    return out


_SELECT = """
    SELECT p.publication_id::text AS publication_id, p.version, p.eet_version, p.uses, p.reference_date, p.status,
           p.payload, p.payload_sha256, p.completeness, p.prepared_at, p.decided_at, p.decision_reason,
           p.approval_request_id::text AS approval_request_id, mk.full_name AS prepared_by_name, ck.full_name AS decided_by_name
    FROM eet_publications p LEFT JOIN users mk ON mk.user_id = p.prepared_by LEFT JOIN users ck ON ck.user_id = p.decided_by
    WHERE p.org_id = CAST(:o AS uuid)"""


def list_versions(session: Session, org_id: str) -> list[dict]:
    rows = session.execute(text(_SELECT + " ORDER BY p.version DESC"), {"o": org_id}).mappings().all()
    return [_row(r, False) for r in rows]


def get(session: Session, org_id: str, publication_id: str, with_payload: bool = True) -> dict:
    r = session.execute(text(_SELECT + " AND p.publication_id = CAST(:p AS uuid)"), {"o": org_id, "p": publication_id}).mappings().first()
    if not r:
        raise EETError("EET version not found")
    return _row(r, with_payload)


def changes(session: Session, org_id: str) -> dict:
    """What a fresh EET would change against the latest PUBLISHED version (same uses)."""
    last = session.execute(text(_SELECT + " AND p.status = 'published' ORDER BY p.version DESC LIMIT 1"),
                           {"o": org_id}).mappings().first()
    if not last:
        return {"published": None}
    fresh = build(session, org_id, tuple(last["uses"]))
    old, new = _comparable(last["payload"]["rows"]), _comparable(fresh["rows"])
    added, removed = sorted(set(new) - set(old)), sorted(set(old) - set(new))
    changed = {}
    for isin in set(old) & set(new):
        diff = sorted(k for k in set(old[isin]) | set(new[isin]) if old[isin].get(k) != new[isin].get(k))
        if diff:
            changed[isin] = diff
    return {"published": {"version": last["version"], "publication_id": last["publication_id"]},
            "up_to_date": not (added or removed or changed), "added_share_classes": added,
            "removed_share_classes": removed, "changed": {k: v[:25] for k, v in changed.items()},
            "n_changed_fields": sum(len(v) for v in changed.values())}


def export(session: Session, org_id: str, publication_id: str, fmt: str) -> tuple[str, str, bytes]:
    pub = get(session, org_id, publication_id)
    if not pub["hash_verified"]:
        raise EETError("this EET version no longer matches its content hash — it can't be sent")
    p = pub["payload"]
    names, rows = p["field_names"], [r["values"] for r in p["rows"]]
    stem = f"EET_{p['eet_version']}_v{pub['version']}_{pub['reference_date']}" + ("" if pub["status"] == "published" else f"_{pub['status'].upper()}")
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(names)
        for r in rows:
            w.writerow([r.get(n, "") for n in names])
        return f"{stem}.csv", "text/csv", buf.getvalue().encode("utf-8")
    if fmt == "xlsx":
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "EET" if pub["status"] == "published" else f"EET {pub['status'].upper()}"
        ws.append(names)
        for r in rows:
            ws.append([_cell(n, r.get(n)) for n in names])
        buf = io.BytesIO()
        wb.save(buf)
        return f"{stem}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buf.getvalue()
    raise EETError("format is xlsx or csv")


def _cell(name: str, v):
    """Numbers as numbers (so a spreadsheet reads 0.976 as a figure); codes and text stay text ('08' stays '08')."""
    if v is None or F.kind(F.by_name()[name]) not in ("proportion", "number", "integer"):
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        return v
