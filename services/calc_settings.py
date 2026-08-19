"""Per-org calculation-method settings — the governed interpretation layer.

Two kinds of setting live here, resolved into one flat dict by `get_calc_settings`:

  * three legacy typed columns on `org_calc_settings` (severity_model / assetmgmt_var_method /
    insurance_return_period_model), unchanged; and
  * an open-ended `interpretation` JSONB whose keys are defined by INTERPRETATION_SCHEMA below — the places a
    regulation genuinely leaves to the institution's business model (e.g. the catastrophe PML return period,
    where Solvency II uses 1-in-200 but a rating agency uses 1-in-250). A new switch is added by extending the
    schema — no migration, no new column.

Every switch has a documented default that reproduces today's behaviour, an allowed set / range that is
validated on write, and a human label + description for the settings UI. Changes route through
services.governance.config_governance (audit + optional 4-eyes), and the RESOLVED settings are stamped onto
every frozen filing snapshot (report_snapshots.engine_versions), so a regulator can see exactly which
interpretation produced each filed number.

The r²≥0.40 crop-publish floor is deliberately NOT here — it is a non-configurable honesty constant.
"""
from __future__ import annotations

from sqlalchemy import text

# Legacy typed columns (kept as columns for backward compatibility).
_TYPED_DEFAULTS = {
    "severity_model": "universal",
    "assetmgmt_var_method": "haircut",
    "insurance_return_period_model": "fixed",
}

# The interpretation switches — regulation leaves these to the institution. default reproduces today's number.
INTERPRETATION_SCHEMA: dict = {
    "pml_return_period": {
        "default": 250, "kind": "int", "allowed": [100, 200, 250, 500],
        "label": "Catastrophe PML return period (years)",
        "description": "Return period for the probable maximum loss. Solvency II SCR is 1-in-200 (99.5% VaR); "
                       "rating agencies commonly use 1-in-250.",
        "sectors": ["insurer"],
    },
    "insurance_expense_ratio": {
        "default": 0.25, "kind": "float", "min": 0.0, "max": 0.6,
        "label": "Insurance expense ratio",
        "description": "Share of gross premium absorbed by expenses; loads the technical premium. Insurer-specific.",
        "sectors": ["insurer"],
    },
    "insurance_profit_margin": {
        "default": 0.05, "kind": "float", "min": 0.0, "max": 0.4,
        "label": "Insurance profit margin",
        "description": "Target underwriting profit margin loaded onto the premium. Insurer-specific.",
        "sectors": ["insurer"],
    },
    "climate_var_dependence": {
        "default": "independent", "kind": "enum", "allowed": ["independent", "additive", "max"],
        "label": "Physical × transition loss dependence (combined VaR)",
        "description": "How physical and transition losses combine on a holding: 'independent' = "
                       "1−(1−physical)(1−transition); 'additive' = min(1, physical+transition), a conservative "
                       "stack; 'max' = the larger driver only.",
        "sectors": ["asset_manager"],
    },
    "resourcing_reallocation_cap_pct": {
        "default": 30, "kind": "int", "min": 5, "max": 100,
        "label": "Re-sourcing reallocation cap (%)",
        "description": "Maximum share of a commodity's spend assumed shiftable to a lower-risk origin near-term.",
        "sectors": ["manufacturer"],
    },
    "adaptation_scenario": {
        "default": "reference", "kind": "enum", "allowed": ["conservative", "reference", "optimistic"],
        "label": "Adaptation effectiveness scenario",
        "description": "How much of the physical loss a resilience retrofit is assumed to avoid: conservative / "
                       "reference (EU Climate-ADAPT / IPCC AR6 WGII central) / optimistic.",
        "sectors": ["reit"],
    },
    "equity_consolidation": {
        "default": "economic_share", "kind": "enum", "allowed": ["economic_share", "excluded", "full"],
        "label": "Equity-method consolidation treatment",
        "description": "How an equity-method associate's climate risk consolidates upward. 'economic_share' = "
                       "the parent's ownership share of the associate's book (the economic-exposure view); "
                       "'excluded' = not in the consolidated book (strict IFRS — an associate's assets aren't "
                       "line-by-line consolidated); 'full' = the whole book (only correct for a controlled sub).",
    },
}

DEFAULTS = {**_TYPED_DEFAULTS, **{k: v["default"] for k, v in INTERPRETATION_SCHEMA.items()}}


def _interpretation_defaults() -> dict:
    return {k: v["default"] for k, v in INTERPRETATION_SCHEMA.items()}


def validate_interpretation(key: str, value):
    """Validate a single interpretation value against its schema. Returns the coerced value or raises
    ValueError. Unknown keys raise (so a typo can't silently store a dead switch)."""
    spec = INTERPRETATION_SCHEMA.get(key)
    if spec is None:
        raise ValueError(f"unknown interpretation setting '{key}'")
    kind = spec["kind"]
    if kind == "enum":
        if value not in spec["allowed"]:
            raise ValueError(f"{key} must be one of {spec['allowed']}")
        return value
    if kind == "int":
        v = int(value)
        if "allowed" in spec and v not in spec["allowed"]:
            raise ValueError(f"{key} must be one of {spec['allowed']}")
        if "min" in spec and v < spec["min"] or "max" in spec and v > spec["max"]:
            raise ValueError(f"{key} must be in [{spec.get('min')}, {spec.get('max')}]")
        return v
    if kind == "float":
        v = float(value)
        if "min" in spec and v < spec["min"] or "max" in spec and v > spec["max"]:
            raise ValueError(f"{key} must be in [{spec.get('min')}, {spec.get('max')}]")
        return v
    raise ValueError(f"unhandled schema kind '{kind}'")


def get_calc_settings(session, org_id: str) -> dict:
    """One flat dict: the three typed methods + every interpretation switch resolved (stored value over
    default). An org that never configured anything gets exactly today's behaviour."""
    row = session.execute(text("""
        SELECT severity_model, assetmgmt_var_method, insurance_return_period_model,
               COALESCE(interpretation, '{}'::jsonb) AS interpretation
        FROM org_calc_settings WHERE org_id = :o
    """), {"o": org_id}).mappings().first()
    if not row:
        return dict(DEFAULTS)
    stored = row["interpretation"] or {}
    resolved = {**_interpretation_defaults(), **{k: stored[k] for k in INTERPRETATION_SCHEMA if k in stored}}
    return {"severity_model": row["severity_model"], "assetmgmt_var_method": row["assetmgmt_var_method"],
            "insurance_return_period_model": row["insurance_return_period_model"], **resolved}


def upsert_calc_settings(session, org_id: str, updates: dict, updated_by: str) -> dict:
    """updates: any subset of the typed keys and/or interpretation keys. Typed keys write their column;
    interpretation keys are validated and merged into the JSONB. Unspecified settings keep their current value."""
    current = get_calc_settings(session, org_id)
    typed = {k: updates.get(k, current[k]) for k in _TYPED_DEFAULTS}

    # start from the currently-stored interpretation, apply validated updates
    stored_row = session.execute(text(
        "SELECT COALESCE(interpretation, '{}'::jsonb) AS i FROM org_calc_settings WHERE org_id = :o"
    ), {"o": org_id}).scalar()
    interp = dict(stored_row or {})
    for k, v in updates.items():
        if k in INTERPRETATION_SCHEMA:
            interp[k] = validate_interpretation(k, v)

    import json
    session.execute(text("""
        INSERT INTO org_calc_settings
            (org_id, severity_model, assetmgmt_var_method, insurance_return_period_model, interpretation, updated_by, updated_at)
        VALUES (:o, :sm, :vm, :rp, CAST(:it AS jsonb), :u, now())
        ON CONFLICT (org_id) DO UPDATE SET
            severity_model = EXCLUDED.severity_model,
            assetmgmt_var_method = EXCLUDED.assetmgmt_var_method,
            insurance_return_period_model = EXCLUDED.insurance_return_period_model,
            interpretation = EXCLUDED.interpretation,
            updated_by = EXCLUDED.updated_by,
            updated_at = now()
    """), {"o": org_id, "sm": typed["severity_model"], "vm": typed["assetmgmt_var_method"],
           "rp": typed["insurance_return_period_model"], "it": json.dumps(interp), "u": updated_by})
    return get_calc_settings(session, org_id)


def interpretation_catalog(org_type: str | None = None) -> list[dict]:
    """The schema as a UI catalog — each switch's key, label, description, default, allowed/range, and current
    applicability. Filtered to a sector when given (a switch with no 'sectors' applies to all)."""
    out = []
    for key, spec in INTERPRETATION_SCHEMA.items():
        sectors = spec.get("sectors")
        if org_type and sectors and org_type not in sectors:
            continue
        out.append({"key": key, "label": spec["label"], "description": spec["description"],
                    "default": spec["default"], "kind": spec["kind"],
                    "allowed": spec.get("allowed"), "min": spec.get("min"), "max": spec.get("max"),
                    "sectors": sectors})
    return out
