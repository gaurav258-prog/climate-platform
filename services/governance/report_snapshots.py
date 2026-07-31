"""Freeze an ESRS/CSRD filing as an immutable, versioned snapshot.

A filed disclosure must be reproducible: the same figures, on the same reporting basis, from the same
golden-source state — even after the live engine has moved on. This service computes the report at the
org's current basis and writes it once into `report_snapshots` (append-only: no update, no delete path).
A correction is a new version, so the history is complete and auditable.

Honesty carries through unchanged: the frozen payload is exactly what the assembler produced — a euro is
a firm figure only where the hazard→yield/asset chain is validated; otherwise exposure is mapped and the €
withheld. Freezing never launders an unvalidated number into a firm one.
"""
from __future__ import annotations

import hashlib
import json
import subprocess

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.governance.reporting_settings import get_settings


def _canonical(obj) -> str:
    """Deterministic JSON for content-hashing — stable key order + compact separators.
    MUST match the back-fill in migration snapshot_worm_20260731."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(obj) -> str:
    return hashlib.sha256(_canonical(obj).encode("utf-8")).hexdigest()


def _git_sha() -> str | None:
    """Short code version, best-effort (None if git is unavailable)."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=".", stderr=subprocess.DEVNULL, timeout=3
        ).decode().strip() or None
    except Exception:  # noqa: BLE001
        return None


def _engine_versions(session: Session) -> dict:
    """The model/data/code versions in force at freeze — so the exact computation is identifiable."""
    from services.intelligence.supply_cogs import IMPACT_VERSION, RANGED_PUBLISH_FLOOR
    from services.data.feeds import FEEDS, basis_freshness_at
    fit_versions = sorted(v for v in session.execute(
        text("SELECT DISTINCT fit_version FROM sc_commodity_fit WHERE fit_version IS NOT NULL")
    ).scalars().all())
    return {
        "impact_version": IMPACT_VERSION,
        "ranged_floor": RANGED_PUBLISH_FLOOR,
        "ranged_gate_metric": "r2_oos",          # gate is out-of-sample r² (audit F2)
        "fit_versions": fit_versions,
        "feed_maturity": {f["key"]: f.get("maturity") for f in FEEDS},
        "feed_freshness_at_freeze": basis_freshness_at(session),   # audit T4: how current the golden source was
        "code_version": _git_sha(),
    }

# report_type -> (human label, builder). The builder takes (session, org_id, scenario, horizon, material).
_BUILDERS = {
    "csrd_e1": ("CSRD · ESRS E1 physical-risk report",
                lambda s, o, sc, hz, m: _csrd_e1(s, o, sc, hz, m)),
    "esrs_pack": ("ESRS Climate & Nature pack (E1 · E3 · E4)",
                  lambda s, o, sc, hz, m: _esrs_pack(s, o, sc, hz, m)),
}


def _csrd_e1(session, org_id, scenario, horizon, material):
    from services.intelligence.csrd_e1 import build_e1_report
    return build_e1_report(session, org_id, scenario=scenario, horizon=horizon, material_threshold=material)


def _esrs_pack(session, org_id, scenario, horizon, material):
    from services.intelligence.esrs_nature import build_esrs_pack
    return build_esrs_pack(session, org_id, scenario=scenario, horizon=horizon, material=material)


def report_types() -> list[dict]:
    return [{"report_type": k, "label": v[0]} for k, v in _BUILDERS.items()]


def create_snapshot(session: Session, org_id: str, report_type: str, actor_user_id: str,
                    note: str | None = None) -> dict:
    """Compute the report at the org's current basis and freeze it as the next version. Immutable once written."""
    if report_type not in _BUILDERS:
        raise ValueError(f"unknown report_type '{report_type}'")
    s = get_settings(session, org_id)
    basis = {"scenario": s["scenario"], "horizon": s["horizon"],
             "materiality_threshold": s["materiality_threshold"], "reporting_period_end": s["reporting_period_end"]}
    payload = _BUILDERS[report_type][1](session, org_id, s["scenario"], s["horizon"], s["materiality_threshold"])
    versions = _engine_versions(session)
    digest = _sha256(payload)

    version = (session.execute(text(
        "SELECT COALESCE(MAX(version), 0) + 1 FROM report_snapshots WHERE org_id = :o AND report_type = :t"),
        {"o": org_id, "t": report_type}).scalar())
    row = session.execute(text("""
        INSERT INTO report_snapshots (org_id, report_type, version, reporting_basis, payload, note, created_by,
                                      payload_sha256, engine_versions)
        VALUES (:o, :t, :v, CAST(:b AS jsonb), CAST(:p AS jsonb), :n, :u, :h, CAST(:ev AS jsonb))
        RETURNING snapshot_id, version, created_at
    """), {"o": org_id, "t": report_type, "v": version,
           "b": json.dumps(basis, default=str), "p": json.dumps(payload, default=str),
           "n": note, "u": actor_user_id, "h": digest, "ev": json.dumps(versions, default=str)}).mappings().first()
    return {"snapshot_id": str(row["snapshot_id"]), "report_type": report_type,
            "label": _BUILDERS[report_type][0], "version": row["version"],
            "reporting_basis": basis, "created_at": row["created_at"].isoformat(), "note": note,
            "payload_sha256": digest, "engine_versions": versions}


def list_snapshots(session: Session, org_id: str, report_type: str | None = None) -> list[dict]:
    """Frozen filings for the org — metadata only (not the full payload), newest first."""
    q = """
        SELECT rs.snapshot_id, rs.report_type, rs.version, rs.reporting_basis, rs.note,
               rs.created_at, u.full_name created_by_name
        FROM report_snapshots rs
        LEFT JOIN users u ON u.user_id = rs.created_by
        WHERE rs.org_id = :o {filt}
        ORDER BY rs.created_at DESC
    """.format(filt="AND rs.report_type = :t" if report_type else "")
    params = {"o": org_id}
    if report_type:
        params["t"] = report_type
    rows = session.execute(text(q), params).mappings().all()
    labels = {k: v[0] for k, v in _BUILDERS.items()}
    return [{"snapshot_id": str(r["snapshot_id"]), "report_type": r["report_type"],
             "label": labels.get(r["report_type"], r["report_type"]), "version": r["version"],
             "reporting_basis": r["reporting_basis"], "note": r["note"],
             "created_at": r["created_at"].isoformat(), "created_by": r["created_by_name"]} for r in rows]


def get_snapshot(session: Session, org_id: str, snapshot_id: str) -> dict | None:
    """One frozen filing, with its full payload — the exact bytes as filed."""
    r = session.execute(text("""
        SELECT rs.snapshot_id, rs.report_type, rs.version, rs.reporting_basis, rs.payload,
               rs.note, rs.created_at, rs.payload_sha256, rs.engine_versions, u.full_name created_by_name
        FROM report_snapshots rs
        LEFT JOIN users u ON u.user_id = rs.created_by
        WHERE rs.org_id = :o AND rs.snapshot_id = :s
    """), {"o": org_id, "s": snapshot_id}).mappings().first()
    if not r:
        return None
    labels = {k: v[0] for k, v in _BUILDERS.items()}
    # re-verify the content hash: the stored payload must still hash to what was signed off
    recomputed = _sha256(r["payload"])
    return {"snapshot_id": str(r["snapshot_id"]), "report_type": r["report_type"],
            "label": labels.get(r["report_type"], r["report_type"]), "version": r["version"],
            "reporting_basis": r["reporting_basis"], "payload": r["payload"], "note": r["note"],
            "created_at": r["created_at"].isoformat(), "created_by": r["created_by_name"],
            "payload_sha256": r["payload_sha256"], "engine_versions": r["engine_versions"],
            "hash_verified": (r["payload_sha256"] is not None and r["payload_sha256"] == recomputed)}
