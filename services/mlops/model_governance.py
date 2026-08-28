"""Model governance — the lifecycle, approval gate, drift monitoring and rollback for the model registry.

A scoring model version moves candidate → approved → active → retired, with an optional *challenger* running
beside the active one. The one hard control: a version is only APPROVED once its out-of-sample calibration
clears the publish gate (r² ≥ 0.40) — the same honesty standard the product publishes on, enforced here as a
promotion gate so an under-calibrated model can never become the active scorer. Every transition is written
append-only to `model_status_event` (audit + rollback trail); `superseded_by` links a retired version to the
one that replaced it, so a rollback is simply re-activating a prior model_id.

Built on the existing `model_registry` table (see core/db/models.ModelRegistry). Raw-SQL via the session,
matching the platform's other governance services.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

PUBLISH_GATE_R2 = 0.40  # the honesty gate — must match ml calibration; below this a model cannot be approved


class GovernanceError(ValueError):
    """A lifecycle transition was rejected (gate not met, wrong state, unknown model)."""


def meets_publish_gate(r2_oos: Optional[float]) -> bool:
    """The publish/approval gate: an out-of-sample r² at or above 0.40. None never passes."""
    return r2_oos is not None and float(r2_oos) >= PUBLISH_GATE_R2


def _event(s: Session, model_id: str, hazard: str, to_status: str, *, from_status: Optional[str] = None,
           actor: Optional[str] = None, reason: Optional[str] = None, r2: Optional[float] = None) -> None:
    s.execute(text("""
        INSERT INTO model_status_event (event_id, model_id, hazard_type, from_status, to_status, actor, reason, r2_oos)
        VALUES (gen_random_uuid(), CAST(:m AS uuid), :h, :fs, :ts, :a, :r, :r2)
    """), {"m": model_id, "h": hazard, "fs": from_status, "ts": to_status, "a": actor, "r": reason, "r2": r2})


def _get(s: Session, model_id: str) -> dict:
    row = s.execute(text("""
        SELECT model_id::text, hazard_type, lifecycle_status, r2_oos, is_active
        FROM model_registry WHERE model_id = CAST(:m AS uuid)
    """), {"m": model_id}).mappings().first()
    if not row:
        raise GovernanceError(f"unknown model_id {model_id}")
    return dict(row)


def register_candidate(s: Session, *, model_version: str, hazard_type: str, algorithm: str,
                       training_data_vintage: str, r2_oos: Optional[float] = None,
                       validation_auc: Optional[float] = None, calibration_note: Optional[str] = None,
                       actor: Optional[str] = None) -> str:
    """Register a new model version as a candidate. Idempotent on model_version."""
    mid = s.execute(text("""
        INSERT INTO model_registry (model_id, model_version, hazard_type, algorithm, training_data_vintage,
                                    validation_auc, r2_oos, calibration_note, lifecycle_status, is_active)
        VALUES (gen_random_uuid(), :v, :h, :alg, :vint, :auc, :r2, :note, 'candidate', false)
        ON CONFLICT (model_version) DO UPDATE SET r2_oos = COALESCE(EXCLUDED.r2_oos, model_registry.r2_oos),
                                                  calibration_note = COALESCE(EXCLUDED.calibration_note, model_registry.calibration_note)
        RETURNING model_id::text
    """), {"v": model_version, "h": hazard_type, "alg": algorithm, "vint": training_data_vintage,
           "auc": validation_auc, "r2": r2_oos, "note": calibration_note}).scalar()
    _event(s, mid, hazard_type, "candidate", actor=actor, reason="registered", r2=r2_oos)
    return mid


def approve(s: Session, model_id: str, *, actor: str, r2_oos: Optional[float] = None,
            note: Optional[str] = None) -> dict:
    """Approve a candidate — GATED on r² ≥ 0.40. Refuses otherwise."""
    m = _get(s, model_id)
    r2 = r2_oos if r2_oos is not None else (float(m["r2_oos"]) if m["r2_oos"] is not None else None)
    if not meets_publish_gate(r2):
        raise GovernanceError(
            f"cannot approve {model_id}: out-of-sample r² {r2} is below the publish gate {PUBLISH_GATE_R2}")
    s.execute(text("""
        UPDATE model_registry SET lifecycle_status='approved', approved_at=now(), approved_by=:a,
               r2_oos=:r2, calibration_note=COALESCE(:note, calibration_note)
        WHERE model_id = CAST(:m AS uuid)
    """), {"a": actor, "r2": r2, "note": note, "m": model_id})
    _event(s, model_id, m["hazard_type"], "approved", from_status=m["lifecycle_status"], actor=actor, r2=r2)
    return _get(s, model_id)


def _retire_active(s: Session, hazard: str, *, superseded_by: Optional[str], actor: str, reason: str) -> None:
    """Retire whichever version is currently active for a hazard (records the transition)."""
    cur = s.execute(text("""
        SELECT model_id::text, lifecycle_status FROM model_registry
        WHERE hazard_type = :h AND is_active = true
    """), {"h": hazard}).mappings().all()
    for row in cur:
        s.execute(text("""
            UPDATE model_registry SET lifecycle_status='retired', is_active=false, retired_at=now(),
                   superseded_by = CAST(:sb AS uuid)
            WHERE model_id = CAST(:m AS uuid)
        """), {"sb": superseded_by, "m": row["model_id"]})
        _event(s, row["model_id"], hazard, "retired", from_status=row["lifecycle_status"],
               actor=actor, reason=reason)


def activate(s: Session, model_id: str, *, actor: str, reason: str = "promotion") -> dict:
    """Promote an approved (or challenger) version to active, retiring the current active for its hazard."""
    m = _get(s, model_id)
    if m["lifecycle_status"] not in ("approved", "challenger"):
        raise GovernanceError(f"cannot activate {model_id}: status is '{m['lifecycle_status']}', need approved/challenger")
    _retire_active(s, m["hazard_type"], superseded_by=model_id, actor=actor, reason=f"superseded ({reason})")
    s.execute(text("""
        UPDATE model_registry SET lifecycle_status='active', is_active=true, activated_at=now(),
               activated_by=:a, retired_at=NULL, superseded_by=NULL WHERE model_id = CAST(:m AS uuid)
    """), {"a": actor, "m": model_id})
    _event(s, model_id, m["hazard_type"], "active", from_status=m["lifecycle_status"], actor=actor,
           reason=reason, r2=m["r2_oos"])
    return _get(s, model_id)


def set_challenger(s: Session, model_id: str, *, actor: str) -> dict:
    """Mark an approved version as the challenger running beside the active model (shadow / comparison)."""
    m = _get(s, model_id)
    if m["lifecycle_status"] not in ("approved", "candidate"):
        raise GovernanceError(f"cannot set challenger {model_id}: status '{m['lifecycle_status']}'")
    if not meets_publish_gate(float(m["r2_oos"]) if m["r2_oos"] is not None else None):
        raise GovernanceError("a challenger must itself clear the publish gate (r² ≥ 0.40)")
    s.execute(text("UPDATE model_registry SET lifecycle_status='challenger' WHERE model_id = CAST(:m AS uuid)"),
              {"m": model_id})
    _event(s, model_id, m["hazard_type"], "challenger", from_status=m["lifecycle_status"], actor=actor)
    return _get(s, model_id)


def promote_challenger(s: Session, hazard_type: str, *, actor: str) -> dict:
    """Promote the hazard's challenger to active (retires the incumbent). The champion/challenger swap."""
    ch = s.execute(text("""
        SELECT model_id::text FROM model_registry WHERE hazard_type=:h AND lifecycle_status='challenger'
        ORDER BY created_at DESC LIMIT 1
    """), {"h": hazard_type}).scalar()
    if not ch:
        raise GovernanceError(f"no challenger registered for hazard '{hazard_type}'")
    return activate(s, ch, actor=actor, reason="challenger promoted")


def rollback(s: Session, hazard_type: str, to_model_id: str, *, actor: str, reason: str) -> dict:
    """Roll back to a previously-approved version for a hazard (re-activates it, retires the current active).

    Only a version that once cleared the gate can be rolled back to — you can never activate an ungated model.
    """
    m = _get(s, to_model_id)
    if m["hazard_type"] != hazard_type:
        raise GovernanceError("target model is for a different hazard")
    if not meets_publish_gate(float(m["r2_oos"]) if m["r2_oos"] is not None else None):
        raise GovernanceError("cannot roll back to a version that never cleared the publish gate")
    # re-approve state so activate() accepts it, then activate with a rollback reason
    s.execute(text("UPDATE model_registry SET lifecycle_status='approved' WHERE model_id = CAST(:m AS uuid)"),
              {"m": to_model_id})
    return activate(s, to_model_id, actor=actor, reason=f"ROLLBACK — {reason}")


def record_drift(s: Session, model_id: str, *, kind: str, metric: str, value: float,
                 threshold: Optional[float] = None, drift_window: Optional[str] = None,
                 note: Optional[str] = None) -> bool:
    """Append a drift observation against a model; returns True if it breached its threshold."""
    m = _get(s, model_id)
    breached = threshold is not None and float(value) > float(threshold)
    s.execute(text("""
        INSERT INTO model_drift_observation (obs_id, model_id, hazard_type, kind, metric, value, threshold, breached, drift_window, note)
        VALUES (gen_random_uuid(), CAST(:m AS uuid), :h, :k, :met, :v, :t, :b, :w, :n)
    """), {"m": model_id, "h": m["hazard_type"], "k": kind, "met": metric, "v": value, "t": threshold,
           "b": breached, "w": drift_window, "n": note})
    return breached


def registry(s: Session, hazard_type: Optional[str] = None) -> list[dict]:
    """Current registry with governance state — for the audit / oversight surface."""
    rows = s.execute(text(f"""
        SELECT model_version, hazard_type, algorithm, lifecycle_status, r2_oos, is_active,
               approved_by, approved_at, activated_by, activated_at, calibration_note, model_id::text
        FROM model_registry {"WHERE hazard_type = :h" if hazard_type else ""}
        ORDER BY hazard_type, created_at DESC
    """), ({"h": hazard_type} if hazard_type else {})).mappings().all()
    return [dict(r) for r in rows]


def drift(s: Session, hazard_type: Optional[str] = None, limit: int = 50) -> list[dict]:
    """Recent drift observations (newest first)."""
    rows = s.execute(text(f"""
        SELECT model_id::text, hazard_type, kind, metric, value, threshold, breached, drift_window, note, created_at
        FROM model_drift_observation {"WHERE hazard_type = :h" if hazard_type else ""}
        ORDER BY created_at DESC LIMIT :lim
    """), ({"h": hazard_type, "lim": limit} if hazard_type else {"lim": limit})).mappings().all()
    return [dict(r) for r in rows]
