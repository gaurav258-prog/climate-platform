"""Lane 2 — provided datapoints: bring-your-own-number, reconciled + attested.

A value computed on the customer's or a vendor's side (own-operations GHG from a carbon tool, a Taxonomy
alignment determination, an audited financed-emissions figure, an ESG indicator) is submitted here. We:
  1. accept it only for a 'provided'-lane datapoint in the canonical catalog (never an arbitrary key),
  2. preserve provenance (source client/vendor, provider name, data vintage),
  3. reconcile it against Tellumen's own computed value where a counterpart exists (delta vs tolerance),
  4. route it through the shared 4-eyes machinery — it is 'pending' until a second person attests it.

Precedence, matching the reference-data model, is client > vendor. Nothing lands in a filing unattested.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.governance.datapoint_catalog import CATALOG

DEFAULT_TOL_PCT = 5.0     # a provided value within ±5% of our baseline reconciles clean, unless the catalog overrides


class ProvidedError(ValueError):
    pass


def _catalog_dp(framework: str, key: str) -> dict | None:
    return next((d for d in (CATALOG.get(framework) or []) if d["key"] == key), None)


def providable(framework: str) -> list[dict]:
    """The datapoints a customer/vendor can provide for a framework — every 'provided'-lane entry (you must
    supply it), plus 'reconcilable' computed entries (optional — bring your own figure to cross-check ours)."""
    return [{"key": d["key"], "label": d["label"], "provider": d["provider"], "note": d["note"],
             "source_category": d["source_category"],
             "kind": "required" if d["lane"] == "provided" else "reconcile"}
            for d in (CATALOG.get(framework) or []) if d["lane"] == "provided" or d.get("reconcilable")]


def _baseline(session: Session, org_id: str, framework: str, key: str) -> float | None:
    """Tellumen's own value for a provided datapoint, where we compute a counterpart — the recon anchor.
    Only the datapoints where we genuinely have a comparable number return a baseline; others reconcile to
    None (stored as provided, no divergence check) — honest, never invented."""
    try:
        from services.governance.reporting_settings import get_settings
        s = get_settings(session, org_id)
        # financed emissions: we compute a PCAF estimate a bank can reconcile its audited figure against
        if framework == "bank_tcfd" and key == "financed_emissions":
            from api.routers.bank import build_disclosure_snapshot
            em = build_disclosure_snapshot(session, org_id, s["scenario"], s["horizon"]).get("financed_emissions_tco2e", {})
            return sum((em.get(k) or 0) for k in ("scope1", "scope2", "scope3")) or None
    except Exception:
        return None
    return None


def submit(session: Session, org_id: str, actor: str, *, framework: str, datapoint_key: str,
           value_num: float | None = None, value_text: str | None = None, unit: str | None = None,
           source: str = "client", provider_name: str | None = None, data_vintage: str | None = None,
           period_label: str | None = None) -> dict:
    """Record a provided value, reconcile it, and raise a 4-eyes attest request."""
    dp = _catalog_dp(framework, datapoint_key)
    if not dp:
        raise ProvidedError(f"unknown datapoint '{datapoint_key}' for {framework}")
    if dp["lane"] != "provided" and not dp.get("reconcilable"):
        raise ProvidedError(f"datapoint '{datapoint_key}' cannot be provided (lane={dp['lane']}); it is computed by Tellumen")
    if source not in ("client", "vendor"):
        raise ProvidedError("source must be 'client' or 'vendor'")
    if value_num is None and not (value_text or "").strip():
        raise ProvidedError("a value (numeric or text) is required")

    # reconcile against our baseline where one exists
    base = _baseline(session, org_id, framework, datapoint_key) if value_num is not None else None
    tol = dp.get("recon_tol") or DEFAULT_TOL_PCT
    delta_pct = within = note = None
    if base is not None and base != 0 and value_num is not None:
        delta_pct = round(100 * (value_num - base) / base, 1)
        within = abs(delta_pct) <= tol
        note = f"Tellumen baseline {base:,.0f}; provided differs {delta_pct:+.1f}% ({'within' if within else 'beyond'} ±{tol:g}% tolerance)."
    elif value_num is not None:
        note = "No Tellumen counterpart to reconcile against — stored as provided, with provenance."

    # supersede any prior live value for this datapoint
    session.execute(text("""
        UPDATE provided_datapoint SET status='superseded'
        WHERE org_id=:o AND framework=:f AND datapoint_key=:k AND status IN ('pending','attested')
    """), {"o": org_id, "f": framework, "k": datapoint_key})

    pid = session.execute(text("""
        INSERT INTO provided_datapoint (org_id, framework, datapoint_key, value_num, value_text, unit, source,
            provider_name, data_vintage, period_label, tellumen_value, delta_pct, within_tolerance, recon_note, submitted_by)
        VALUES (:o,:f,:k,:vn,:vt,:u,:src,:pn, CAST(:dv AS date),:pl,:tv,:dp,:wt,:rn,:by)
        RETURNING provided_id
    """), {"o": org_id, "f": framework, "k": datapoint_key, "vn": value_num, "vt": (value_text or None),
           "u": unit, "src": source, "pn": provider_name, "dv": data_vintage or None, "pl": period_label,
           "tv": base, "dp": delta_pct, "wt": within, "rn": note, "by": actor}).scalar()

    # raise the shared 4-eyes request (checker ≠ maker enforced by the approvals router)
    import json
    payload = {"provided_id": str(pid), "framework": framework, "datapoint_key": datapoint_key,
               "value_num": value_num, "value_text": value_text, "source": source}
    title = f"Attest provided value · {dp['label'][:60]}"
    rid = session.execute(text("""
        INSERT INTO approval_requests (org_id, request_type, title, payload, maker_user_id)
        VALUES (:o,'provided.datapoint',:ti, CAST(:p AS jsonb), :m) RETURNING request_id
    """), {"o": org_id, "ti": title, "p": json.dumps(payload), "m": actor}).scalar()
    session.execute(text("UPDATE provided_datapoint SET approval_request_id=:r WHERE provided_id=:p"),
                    {"r": rid, "p": pid})
    return {"provided_id": str(pid), "status": "pending", "approval_request_id": str(rid),
            "tellumen_value": base, "delta_pct": delta_pct, "within_tolerance": within, "recon_note": note}


def attest(session: Session, org_id: str, payload: dict, decision: str, actor: str) -> dict:
    """Called from the approvals decide handler: attest or reject a provided value."""
    pid = (payload or {}).get("provided_id")
    status = "attested" if decision == "approved" else "rejected"
    session.execute(text("""
        UPDATE provided_datapoint SET status=:s, decided_by=:u, decided_at=now()
        WHERE provided_id=CAST(:p AS uuid) AND org_id=:o AND status='pending'
    """), {"s": status, "u": actor, "p": pid, "o": org_id})
    return {"provided_id": pid, "status": status}


def provided_list(session: Session, org_id: str, framework: str | None = None) -> list[dict]:
    """Live + recent provided values with their recon + attest status."""
    rows = session.execute(text("""
        SELECT p.provided_id::text AS provided_id, p.framework, p.datapoint_key, p.value_num, p.value_text,
               p.unit, p.source, p.provider_name, p.data_vintage, p.tellumen_value, p.delta_pct,
               p.within_tolerance, p.recon_note, p.status, p.submitted_at, su.email AS submitted_by,
               du.email AS decided_by
        FROM provided_datapoint p
        LEFT JOIN users su ON su.user_id = p.submitted_by
        LEFT JOIN users du ON du.user_id = p.decided_by
        WHERE p.org_id = :o AND p.status <> 'superseded' AND (CAST(:f AS text) IS NULL OR p.framework = :f)
        ORDER BY p.submitted_at DESC
    """), {"o": org_id, "f": framework}).mappings().all()
    labels = {d["key"]: d["label"] for fw in CATALOG.values() for d in fw}
    return [{"provided_id": r["provided_id"], "framework": r["framework"], "datapoint_key": r["datapoint_key"],
             "label": labels.get(r["datapoint_key"], r["datapoint_key"]),
             "value_num": r["value_num"], "value_text": r["value_text"], "unit": r["unit"],
             "source": r["source"], "provider_name": r["provider_name"],
             "data_vintage": r["data_vintage"].isoformat() if r["data_vintage"] else None,
             "tellumen_value": r["tellumen_value"], "delta_pct": r["delta_pct"],
             "within_tolerance": r["within_tolerance"], "recon_note": r["recon_note"], "status": r["status"],
             "submitted_by": r["submitted_by"], "decided_by": r["decided_by"],
             "submitted_at": r["submitted_at"].isoformat() if r["submitted_at"] else None} for r in rows]
