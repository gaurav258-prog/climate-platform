"""Per-org calculation-method settings — the governed interpretation layer.

Two kinds of setting live here, resolved into one flat dict by `get_calc_settings`:

  * the typed column assetmgmt_var_method on `org_calc_settings` (the asset manager's VaR method); and
  * an open-ended `interpretation` JSONB whose keys are defined by INTERPRETATION_SCHEMA below — the places a
    regulation genuinely leaves to the institution's business model (e.g. the catastrophe PML return period,
    where Solvency II uses 1-in-200 but a rating agency uses 1-in-250). A new switch is added by extending the
    schema — no migration, no new column.

Every switch has a documented default that reproduces today's behaviour, an allowed set / range that is
validated on write, and a label printed with a frozen filing's elections. What each switch decides, and the rule
behind it, are customer words in the message catalogue (admin.switch.<key>, data/reference/messages.en.json) — the
Methodology screen reads them through services.governance.admin_view. Changes route through
services.governance.config_governance (audit + optional 4-eyes), and the RESOLVED settings are stamped onto
every frozen filing snapshot (report_snapshots.engine_versions), so a regulator can see exactly which
interpretation produced each filed number.

The r²≥0.40 crop-publish floor is deliberately NOT here — it is a non-configurable honesty constant.
"""
from __future__ import annotations

from sqlalchemy import text

# Legacy typed columns (kept as columns for backward compatibility).
_TYPED_DEFAULTS = {
    "assetmgmt_var_method": "haircut",
}
# the damage schedule's 'universal / peril-specific' model, the return-period model and the insurer's loadings and
# adaptation scenario are gone (E69): the institution states its own damage ratios, event probabilities, loadings and
# adaptation effectiveness as method parameters (services.money.params) — no platform default remains to choose between

def _orsa_qualifying(which: str) -> list[str]:
    """The platform scenarios that qualify for an Art. 45a(2) scenario — read from data/reference/orsa_climate_scenarios.json."""
    import json
    import os
    with open(os.path.join("data", "reference", "orsa_climate_scenarios.json")) as f:
        ref = json.load(f)
    c = ref["classification"]
    ok = (lambda w: w < c["below_2c_max_best_estimate_c"]) if which == "below_2c" else (lambda w: w >= c["above_2c_min_best_estimate_c"])
    return sorted(k for k, v in ref["scenarios"].items() if ok(v["warming_2081_2100_c"]))


def _loss_families(peril: str) -> list[str]:
    """The damage-curve families a loss may be computed with for this peril: the sound, registered families
    (services.loss.curves; a refused family is never offered)."""
    from services.loss.curves import families
    return sorted(k for k, f in families().items() if f["peril"] == peril)


def _site_weight_switches() -> dict:
    """The holdings look-through (the product owner's decisions of 2026-10-22): a site weight on the assets basis counts
    as a share of the issuer's value; the institution may state that a weight on another measured basis counts too — one
    switch per basis (services.loss.lookthrough.STATED_BASES). No default: not stated, those sites are a named gap. An
    'equal' weight states no measure and is never offered."""
    from services.loss.lookthrough import COUNTS, STATED_BASES, switch
    return {switch(b): {"frameworks": [], "default": None, "kind": "enum", "allowed": [COUNTS, "not_counted"],
                        "label": f"Issuer sites weighted by {b.replace('_', ' ')}: counted as a share of value?",
                        "sectors": ["asset_manager"]} for b in STATED_BASES}


def _p3_t1_statements() -> dict:
    from services.governance.pillar3_t1 import switches
    return switches()


# The interpretation switches — regulation leaves these to the institution. default reproduces today's number.
INTERPRETATION_SCHEMA: dict = {
    "pml_return_period": {
        "frameworks": ["insurer_solvency"],
        "default": None, "kind": "int", "allowed": [100, 200, 250, 500],
        "label": "Catastrophe PML return period (years)",
        "sectors": ["insurer"],
    },
    # Directive 2009/138/EC Art. 45a(2): the undertaking's two long-term climate scenarios (data/reference/orsa_climate_scenarios.json).
    # Below 2 °C: orderly_1_5c (SSP1-2.6, 1.8 °C). Well above: hot_house_3_5c (SSP5-8.5, 4.4 °C), disorderly_2c (SSP2-4.5,
    # 2.7 °C). 'orsa_default' = the reference file's default.
    "orsa_scenario_below_2c": {
        "frameworks": ["insurer_orsa_climate"],
        "default": "orsa_default", "kind": "enum", "allowed": ["orsa_default", *_orsa_qualifying("below_2c")],
        "label": "ORSA climate — the scenario where warming remains below 2 °C",
        "sectors": ["insurer"],
    },
    "orsa_scenario_above_2c": {
        "frameworks": ["insurer_orsa_climate"],
        "default": "orsa_default", "kind": "enum", "allowed": ["orsa_default", *_orsa_qualifying("above_2c")],
        "label": "ORSA climate — the scenario where warming is significantly higher than 2 °C",
        "sectors": ["insurer"],
    },
    # Solvency II nat-cat: the United Kingdom is an Annex V / VII region but, since it left the Union, not in Annex XIII
    # (data/reference/solvency2_natcat_rules.json, declared reading 'United Kingdom').
    "sii_natcat_uk_other_regions": {
        "frameworks": ["insurer_solvency"],
        "default": "region_only", "kind": "enum", "allowed": ["region_only", "region_and_premium"],
        "label": "Solvency II nat-cat — risks in the United Kingdom",
        "sectors": ["insurer"],
    },
    # EU Taxonomy Art. 8: the undertaking's own election under Art. 4 of Delegated Regulation (EU) 2026/73. The switch
    # name and value are the ones the specification's transitional_option declares; regspec.governing() applies it.
    # 'amended_rules' = the 2026/73 templates; 'pre_amendment_rules' = the templates as amended by 2023/2486.
    "taxonomy_2026_73_article_4": {
        "frameworks": ["bank_tcfd", "reit_taxonomy"],
        "default": "amended_rules", "kind": "enum", "allowed": ["amended_rules", "pre_amendment_rules"],
        "label": "EU Taxonomy — financial year starting in 2025",
        "sectors": ["bank", "reit"],
    },
    # ESRS: the undertaking's version for the financial year starting in 2026 (Art. 2 of Delegated Regulation (EU)
    # 2026/1563). The switch and the value that changes the governing version are the ones the specification's
    # transitional_option declares (data/reference/regspec/esrs/dr_2023_2772_as_2025_1416.json); regspec.governing()
    # applies it. The statement must say which version is applied (Art. 2(2)) — the filing states this election.
    "esrs_fy2026_version": {
        "frameworks": ["csrd_e1", "esrs_pack"],
        "default": "dr_2023_2772_as_2025_1416", "kind": "enum",
        "allowed": ["dr_2023_2772_as_2025_1416", "dr_2026_1563", "dr_2023_2772_as_2025_1416_with_2026_1563_reliefs"],
        "label": "ESRS — financial year starting in 2026",
        "sectors": ["manufacturer"],
    },
    # CSRD: whether the undertaking's Member State used the derogation of Art. 5(2) of Directive (EU) 2022/2464 (added by
    # Directive (EU) 2026/470) for the financial years starting in 2025-2026 — national law, stated by the undertaking;
    # no default either way (data/reference/csrd/scope.json 'member_state_derogation').
    "csrd_member_state_derogation": {
        "frameworks": ["esrs_pack"],
        "default": "not_stated", "kind": "enum", "allowed": ["not_stated", "exempted", "not_exempted"],
        "label": "CSRD — Member State derogation for FY 2025-2026",
        "sectors": ["manufacturer"],
    },
    # The loss foundation (E171): which published or measured damage-curve family the institution adopts per peril —
    # its stated method, stamped on what the loss feeds. No default: not adopted, every loss is a named gap.
    "loss_curve_family_flood": {
        "frameworks": [], "default": None, "kind": "enum", "allowed": _loss_families("flood"),
        "label": "Flood damage curves (loss figures)",
        "sectors": ["bank", "insurer", "asset_manager", "reit", "manufacturer"],
    },
    "loss_curve_family_storm": {
        "frameworks": [], "default": None, "kind": "enum", "allowed": _loss_families("storm"),
        "label": "Tropical-cyclone damage curves (loss figures)",
        "sectors": ["bank", "insurer", "asset_manager", "reit", "manufacturer"],
    },
    "loss_flood_dependence": {
        "frameworks": [], "default": None, "kind": "enum", "allowed": ["comonotonic"],
        "label": "How flood losses across the book combine",
        "sectors": ["bank", "insurer", "asset_manager", "reit", "manufacturer"],
    },
    # Flood defences (product owner's decisions, 2026-10-16): both figures are always shown; the institution states
    # which one leads — the one its reporting carries.
    "loss_flood_headline": {
        "frameworks": [], "default": None, "kind": "enum", "allowed": ["defended", "undefended"],
        "label": "Which flood loss leads: defended or undefended",
        "sectors": ["bank", "insurer", "asset_manager", "reit", "manufacturer"],
    },
    **_site_weight_switches(),
    "climate_var_dependence": {
        "frameworks": ["sfdr_pai"],
        "default": None, "kind": "enum", "allowed": ["independent", "additive", "max"],
        "label": "Physical × transition loss dependence (combined VaR)",
        "sectors": ["asset_manager"],
    },
    # Pillar 3 ESG Template 1 columns i-k: the institution's own statements, quoted and offered from
    # data/reference/pillar3/t1_financed_emissions.json (services.governance.pillar3_t1). No default: not stated, the
    # columns are a named gap and the filing is blocked.
    **{key: {"frameworks": ["bank_p3esg"], "default": None, "kind": "enum", "sectors": ["bank"], **spec}
       for key, spec in _p3_t1_statements().items()},
    # FX rate policy (multi-currency phase 2). BALANCES always convert at the closing rate of the book date (IAS 21
    # — not a switch); how yearly FLOWS convert is the institution's choice, stamped on every filing.
    "fx_flow_rate": {
        "frameworks": ["bank_tcfd", "bank_p3esg", "sfdr_pai", "reit_taxonomy", "insurer_solvency", "esrs_pack", "csrd_e1"],
        "default": "period_average", "kind": "enum", "allowed": ["period_average", "closing"],
        "label": "Exchange rate for yearly figures (income, spend, revenue, premiums)",
    },
    "fx_client_rate_tolerance_pct": {
        "frameworks": ["bank_tcfd", "bank_p3esg", "sfdr_pai", "reit_taxonomy", "insurer_solvency", "esrs_pack", "csrd_e1"],
        "default": 1.0, "kind": "float", "min": 0.1, "max": 10.0,
        "label": "Own exchange rates: allowed difference from the official rate (%)",
    },
    "esg_energy_intensity_check_factor": {
        "frameworks": ["sfdr_pai"],
        "default": 10.0, "kind": "float", "min": 2.0, "max": 1000.0,
        "label": "Company energy intensity: how far from the sector average before it is checked (×)",
    },
    "retention_minimum_years": {          # retired report types stay listed: their filings are still kept
        "frameworks": ["bank_tcfd", "bank_p3esg", "assetmgmt_tcfd", "sfdr_pai", "reit_tcfd", "reit_taxonomy",
                       "insurer_climate", "insurer_solvency", "esrs_pack", "csrd_e1"],
        "default": 0, "kind": "int", "min": 0, "max": 50,
        "label": "Your own minimum record retention (years)",
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
    if value is None:
        raise ValueError(f"{key} needs a value — choose one of the allowed settings")
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
        SELECT assetmgmt_var_method, COALESCE(interpretation, '{}'::jsonb) AS interpretation
        FROM org_calc_settings WHERE org_id = :o
    """), {"o": org_id}).mappings().first()
    if not row:
        return dict(DEFAULTS)
    stored = row["interpretation"] or {}
    resolved = {**_interpretation_defaults(), **{k: stored[k] for k in INTERPRETATION_SCHEMA if k in stored}}
    return {"assetmgmt_var_method": row["assetmgmt_var_method"], **resolved}


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
        INSERT INTO org_calc_settings (org_id, assetmgmt_var_method, interpretation, updated_by, updated_at)
        VALUES (:o, :vm, CAST(:it AS jsonb), :u, now())
        ON CONFLICT (org_id) DO UPDATE SET
            assetmgmt_var_method = EXCLUDED.assetmgmt_var_method,
            interpretation = EXCLUDED.interpretation,
            updated_by = EXCLUDED.updated_by,
            updated_at = now()
    """), {"o": org_id, "vm": typed["assetmgmt_var_method"], "it": json.dumps(interp), "u": updated_by})
    return get_calc_settings(session, org_id)


def interpretation_catalog(org_type: str | None = None) -> list[dict]:
    """The schema as a UI catalog — each switch's key, its name and explanation (the catalogue's admin.switch.<key>),
    default, options named, range, and applicability. Filtered to a sector when given (a switch with no 'sectors'
    applies to all)."""
    from services.governance.admin_view import switch_view
    out = []
    for key, spec in INTERPRETATION_SCHEMA.items():
        sectors = spec.get("sectors")
        if org_type and sectors and org_type not in sectors:
            continue
        out.append({**switch_view({"key": key, **spec}), "sectors": sectors})
    return out


def elections_for(session, org_id: str, report_type: str) -> list[dict]:
    """The interpretations that govern a report type, as the organisation holds them when it is frozen: each switch whose
    frameworks include the report type — its label, the value in force, and whether the organisation stated it (else the
    switch's default, or None: not stated). Frozen into the filing's payload, so they are covered by its hash and
    printed with it (report_snapshots.create_snapshot)."""
    row = session.execute(text("SELECT COALESCE(interpretation, '{}'::jsonb) FROM org_calc_settings WHERE org_id = :o"),
                          {"o": org_id}).scalar() or {}
    resolved = get_calc_settings(session, org_id)
    return [{"key": k, "label": spec["label"], "value": resolved.get(k), "stated": k in row}
            for k, spec in INTERPRETATION_SCHEMA.items() if report_type in spec.get("frameworks", [])]
