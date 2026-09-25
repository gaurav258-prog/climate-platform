"""Run the intake controls for a customer batch, enforce the gate, and keep the ledger (ingest_batches).

Every sector's upload / API-push route calls the same three functions:

    ctl = preview_controls(session, org_id, template, raw, df, specs, ...)      # dry run — nothing written
    ctl = begin_import(session, org_id, user_id, template, raw, df, specs, ...) # gate enforced, batch recorded
    ctl.finish(session, n_landed=…, value_landed=…)                             # landing check, batch → imported

`begin_import` raises GateError when the batch is blocked, or needs sign-off and none was given — the caller
turns it into a 409 carrying the full control report, so the person sees exactly what to fix or accept.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.ingest import batch_controls as bc
from services.ingest.upload_validation import enrich_specs, validate_table

MIN_SIGNOFF_REASON = 10


class GateError(Exception):
    def __init__(self, code: str, message: str, controls: dict):
        super().__init__(message)
        self.code, self.message, self.controls = code, message, controls

    def detail(self) -> dict:
        return {"error": self.code, "message": self.message, "controls": self.controls}


@dataclass
class IntakeResult:
    controls: dict                     # what the API returns: receipt / transformation / gate (+ landing once finished)
    clean_df: pd.DataFrame             # the accepted rows, normalised — the ONLY rows the sector ingest may read
    report: dict                       # the validator's report (errors, counts)
    sha256: str
    batch_id: Optional[str] = None
    value_field: Optional[str] = None
    value_valid: Optional[float] = None
    n_valid: int = 0
    _finished: bool = field(default=False, repr=False)

    def finish(self, session: Session, *, n_landed: int, value_landed: Optional[float] = None) -> dict:
        landing = bc.landing_check(n_valid=self.n_valid, n_landed=n_landed, value_valid=self.value_valid,
                                   value_landed=value_landed)
        self.controls["landing"] = landing
        if self.batch_id:
            session.execute(text("""
                UPDATE ingest_batches SET status = 'imported', imported_at = now(), landing = CAST(:l AS jsonb)
                WHERE batch_id = CAST(:b AS uuid)
            """), {"l": json.dumps(landing), "b": self.batch_id})
        self._finished = True
        return landing


def parse_declared(row_count, totals_json) -> Optional[dict]:
    """Form inputs → the declared-controls dict. Raises ValueError with a plain message on bad input."""
    out: dict = {}
    if row_count not in (None, ""):
        try:
            out["row_count"] = int(row_count)
        except (TypeError, ValueError):
            raise ValueError("declared_row_count must be a whole number")
    if totals_json not in (None, ""):
        try:
            t = json.loads(totals_json) if isinstance(totals_json, str) else dict(totals_json)
        except (ValueError, TypeError):
            raise ValueError('declared_totals must be JSON like {"appraised_value_eur": 1250000000}')
        if not isinstance(t, dict):
            raise ValueError("declared_totals must be an object of field → total")
        out["control_totals"] = t
    return out or None


def _prior_import(session: Session, org_id: str, template: str, sha: str) -> Optional[dict]:
    r = session.execute(text("""
        SELECT batch_id::text AS batch_id, received_at, imported_at FROM ingest_batches
        WHERE org_id = CAST(:o AS uuid) AND template = :t AND sha256 = :s AND status = 'imported'
        ORDER BY imported_at DESC NULLS LAST LIMIT 1
    """), {"o": org_id, "t": template, "s": sha}).mappings().first()
    return ({"batch_id": r["batch_id"], "received_at": str(r["received_at"])[:19],
             "imported_at": str(r["imported_at"])[:19] if r["imported_at"] else None} if r else None)


def _run(session: Session, org_id: str, template: str, raw: bytes, df: pd.DataFrame, specs: list[dict], *,
         declared: Optional[dict], value_field: Optional[str], thresholds: Optional[dict]) -> IntakeResult:
    specs = enrich_specs(specs)
    sha = bc.sha256_hex(raw)
    report = validate_table(df, specs)
    normalised = bc.normalise_rows(report["valid_rows"], specs)
    receipt = bc.receipt_check(df, declared=declared, duplicate_of=_prior_import(session, org_id, template, sha),
                               thresholds=thresholds)
    transform = bc.transformation_check(df, specs, report, normalised, value_field=value_field, thresholds=thresholds)
    gate = bc.evaluate_gate(receipt, transform, report["n_valid"], thresholds)
    vf = value_field if value_field and value_field in df.columns else None
    value_valid = float(sum(v for v in (n.get(vf) for n in normalised) if isinstance(v, (int, float)))) if vf else None
    controls = {"receipt": receipt, "transformation": transform, "gate": gate}
    return IntakeResult(controls=controls, clean_df=pd.DataFrame(normalised), report=report, sha256=sha,
                        value_field=vf, value_valid=value_valid, n_valid=report["n_valid"])


def preview_controls(session: Session, org_id: str, template: str, raw: bytes, df: pd.DataFrame, specs: list[dict], *,
                     declared: Optional[dict] = None, value_field: Optional[str] = None,
                     thresholds: Optional[dict] = None) -> IntakeResult:
    """Dry run: every control, nothing written."""
    return _run(session, org_id, template, raw, df, specs, declared=declared, value_field=value_field, thresholds=thresholds)


def begin_import(session: Session, org_id: str, user_id: Optional[str], template: str, raw: bytes, df: pd.DataFrame,
                 specs: list[dict], *, filename: Optional[str] = None, via: str = "upload",
                 declared: Optional[dict] = None, value_field: Optional[str] = None, signoff_reason: Optional[str] = None,
                 thresholds: Optional[dict] = None) -> IntakeResult:
    res = _run(session, org_id, template, raw, df, specs, declared=declared, value_field=value_field, thresholds=thresholds)
    gate = res.controls["gate"]
    if gate["status"] == "blocked":
        raise GateError("gate_blocked", "None of the rows passed validation, so nothing can be imported.", res.controls)
    reason = (signoff_reason or "").strip()
    if gate["status"] == "needs_signoff":
        if user_id is None:
            raise GateError("gate_signoff_required",
                            "This batch failed a control and needs a named person's sign-off; API tokens cannot sign off.", res.controls)
        if len(reason) < MIN_SIGNOFF_REASON:
            raise GateError("gate_signoff_required",
                            f"This batch failed a control. To import it anyway, a named person must accept the reasons "
                            f"(signoff_reason, at least {MIN_SIGNOFF_REASON} characters).", res.controls)
    r = res.report
    row = session.execute(text("""
        INSERT INTO ingest_batches (org_id, template, via, filename, sha256, received_by, declared, n_total, n_valid, n_rejected,
                                    value_field, value_valid, receipt, transform, gate_status, gate_reasons, signoff_by, signoff_reason)
        VALUES (CAST(:o AS uuid), :t, :via, :f, :s, CAST(:u AS uuid), CAST(:d AS jsonb), :nt, :nv, :ne, :vf, :vv,
                CAST(:rc AS jsonb), CAST(:tr AS jsonb), :g, CAST(:gr AS jsonb), CAST(:so AS uuid), :sr)
        RETURNING batch_id::text
    """), {"o": org_id, "t": template, "via": via, "f": filename, "s": res.sha256, "u": user_id,
           "d": json.dumps(declared or {}), "nt": r["n_total"], "nv": r["n_valid"], "ne": r["n_error"],
           "vf": res.value_field, "vv": res.value_valid, "rc": json.dumps(res.controls["receipt"], default=str),
           "tr": json.dumps(res.controls["transformation"], default=str), "g": gate["status"],
           "gr": json.dumps(gate["reasons"]), "so": user_id if gate["status"] == "needs_signoff" else None,
           "sr": reason if gate["status"] == "needs_signoff" else None}).scalar()
    res.batch_id = str(row)
    res.controls["batch_id"] = res.batch_id
    return res


def list_batches(session: Session, org_id: str, limit: int = 50) -> list[dict]:
    rows = session.execute(text("""
        SELECT batch_id::text, template, via, filename, received_at, n_total, n_valid, n_rejected, gate_status, status,
               signoff_reason, (landing->>'n_dropped_after_validation')::int AS n_dropped
        FROM ingest_batches WHERE org_id = CAST(:o AS uuid) ORDER BY received_at DESC LIMIT :l
    """), {"o": org_id, "l": limit}).mappings().all()
    return [{**dict(r), "received_at": str(r["received_at"])[:19]} for r in rows]


def get_batch(session: Session, org_id: str, batch_id: str) -> Optional[dict]:
    r = session.execute(text("""
        SELECT batch_id::text, template, via, filename, sha256, received_at, imported_at, declared, n_total, n_valid, n_rejected,
               value_field, value_valid, receipt, transform, gate_status, gate_reasons, signoff_by::text, signoff_reason, status, landing
        FROM ingest_batches WHERE org_id = CAST(:o AS uuid) AND batch_id = CAST(:b AS uuid)
    """), {"o": org_id, "b": batch_id}).mappings().first()
    if not r:
        return None
    d = dict(r)
    d["received_at"] = str(d["received_at"])[:19]
    d["imported_at"] = str(d["imported_at"])[:19] if d["imported_at"] else None
    return d
