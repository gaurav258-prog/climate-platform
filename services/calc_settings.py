"""Per-org calculation-method triggers (see the org_calc_settings migration).

A single read + a single write, reused by every vertical router so there's
one place that knows the default row (an org that never configured anything
gets exactly today's behaviour, not a KeyError).
"""
from __future__ import annotations

from sqlalchemy import text

DEFAULTS = {
    "severity_model": "universal",
    "assetmgmt_var_method": "haircut",
    "insurance_return_period_model": "fixed",
}


def get_calc_settings(session, org_id: str) -> dict:
    row = session.execute(text("""
        SELECT severity_model, assetmgmt_var_method, insurance_return_period_model
        FROM org_calc_settings WHERE org_id = :o
    """), {"o": org_id}).mappings().first()
    return dict(row) if row else dict(DEFAULTS)


def upsert_calc_settings(session, org_id: str, updates: dict, updated_by: str) -> dict:
    """updates: any subset of DEFAULTS' keys. Unspecified fields keep their
    current value (or the default, on first write)."""
    current = get_calc_settings(session, org_id)
    merged = {**current, **{k: v for k, v in updates.items() if k in DEFAULTS}}
    session.execute(text("""
        INSERT INTO org_calc_settings
            (org_id, severity_model, assetmgmt_var_method, insurance_return_period_model, updated_by, updated_at)
        VALUES (:o, :sm, :vm, :rp, :u, now())
        ON CONFLICT (org_id) DO UPDATE SET
            severity_model = EXCLUDED.severity_model,
            assetmgmt_var_method = EXCLUDED.assetmgmt_var_method,
            insurance_return_period_model = EXCLUDED.insurance_return_period_model,
            updated_by = EXCLUDED.updated_by,
            updated_at = now()
    """), {"o": org_id, "sm": merged["severity_model"], "vm": merged["assetmgmt_var_method"],
           "rp": merged["insurance_return_period_model"], "u": updated_by})
    return merged
