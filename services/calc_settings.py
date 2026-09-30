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

def _orsa_qualifying(which: str) -> list[str]:
    """The platform scenarios that qualify for an Art. 45a(2) scenario — read from data/reference/orsa_climate_scenarios.json."""
    import json
    import os
    with open(os.path.join("data", "reference", "orsa_climate_scenarios.json")) as f:
        ref = json.load(f)
    c = ref["classification"]
    ok = (lambda w: w < c["below_2c_max_best_estimate_c"]) if which == "below_2c" else (lambda w: w >= c["above_2c_min_best_estimate_c"])
    return sorted(k for k, v in ref["scenarios"].items() if ok(v["warming_2081_2100_c"]))


# The interpretation switches — regulation leaves these to the institution. default reproduces today's number.
INTERPRETATION_SCHEMA: dict = {
    "pml_return_period": {
        "frameworks": ["insurer_climate", "insurer_solvency"],
        "default": 250, "kind": "int", "allowed": [100, 200, 250, 500],
        "label": "Catastrophe PML return period (years)",
        "description": "Return period for the probable maximum loss. Solvency II SCR is 1-in-200 (99.5% VaR); "
                       "rating agencies commonly use 1-in-250.",
        "sectors": ["insurer"],
    },
    "insurance_expense_ratio": {
        "frameworks": ["insurer_solvency"],
        "default": 0.25, "kind": "float", "min": 0.0, "max": 0.6,
        "label": "Insurance expense ratio",
        "description": "Share of gross premium absorbed by expenses; loads the technical premium. Insurer-specific.",
        "sectors": ["insurer"],
    },
    "insurance_profit_margin": {
        "frameworks": ["insurer_solvency"],
        "default": 0.05, "kind": "float", "min": 0.0, "max": 0.4,
        "label": "Insurance profit margin",
        "description": "Target underwriting profit margin loaded onto the premium. Insurer-specific.",
        "sectors": ["insurer"],
    },
    # Directive 2009/138/EC Art. 45a(2): the undertaking's two long-term climate scenarios (data/reference/orsa_climate_scenarios.json)
    "orsa_scenario_below_2c": {
        "frameworks": ["insurer_orsa_climate"],
        "default": "orsa_default", "kind": "enum", "allowed": ["orsa_default", *_orsa_qualifying("below_2c")],
        "label": "ORSA climate — the scenario where warming remains below 2 °C",
        "description": "Art. 45a(2)(a). Only scenarios whose long-term warming (IPCC AR6 best estimate) is below 2.0 °C qualify: "
                       "orderly_1_5c (SSP1-2.6, 1.8 °C). 'orsa_default' = the reference file's default.",
        "sectors": ["insurer"],
    },
    "orsa_scenario_above_2c": {
        "frameworks": ["insurer_orsa_climate"],
        "default": "orsa_default", "kind": "enum", "allowed": ["orsa_default", *_orsa_qualifying("above_2c")],
        "label": "ORSA climate — the scenario where warming is significantly higher than 2 °C",
        "description": "Art. 45a(2)(b). Scenarios with long-term warming of at least 2.5 °C qualify: hot_house_3_5c (SSP5-8.5, "
                       "4.4 °C) or disorderly_2c (SSP2-4.5, 2.7 °C). 'orsa_default' = the reference file's default.",
        "sectors": ["insurer"],
    },
    # Solvency II nat-cat: the United Kingdom is an Annex V / VII region but, since it left the Union, not in Annex XIII
    # (data/reference/solvency2_natcat_rules.json, declared reading 'United Kingdom').
    "sii_natcat_uk_other_regions": {
        "frameworks": ["insurer_solvency"],
        "default": "region_only", "kind": "enum", "allowed": ["region_only", "region_and_premium"],
        "label": "Solvency II nat-cat — risks in the United Kingdom",
        "description": "The UK is a windstorm and flood region of Del. Reg. 2015/35 (Annexes V, VII) but is not listed in "
                       "Annex XIII. 'region_only' = the regional charge only (the Annex gives the region a factor); "
                       "'region_and_premium' = the literal reading, adding the premium-based charge for regions outside "
                       "Annex XIII.",
        "sectors": ["insurer"],
    },
    # EU Taxonomy Art. 8: the undertaking's own election under Art. 4 of Delegated Regulation (EU) 2026/73. The switch
    # name and value are the ones the specification's transitional_option declares; regspec.governing() applies it.
    "taxonomy_2026_73_article_4": {
        "frameworks": ["bank_tcfd", "reit_taxonomy"],
        "default": "amended_rules", "kind": "enum", "allowed": ["amended_rules", "pre_amendment_rules"],
        "label": "EU Taxonomy — financial year starting in 2025",
        "description": "Delegated Regulation (EU) 2026/73, Art. 4: undertakings may apply the Taxonomy delegated "
                       "regulations as applicable on 31 December 2025 for the financial year that starts in 2025. "
                       "'amended_rules' = the 2026/73 templates; 'pre_amendment_rules' = the templates as amended by "
                       "2023/2486. Other financial years are unaffected.",
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
        "description": "Delegated Regulation (EU) 2026/1563, Art. 2: for the financial year starting in 2026 the "
                       "undertaking may apply (a) the ESRS as amended by 2025/1416, or the ESRS as amended by 2026/1563, "
                       "or (b) the ESRS as amended by 2025/1416 with the reliefs of Art. 2(1)(b) (ESRS 1 §27, 32-33, "
                       "74-75, 90, 91, 92, 106, 110). The sustainability statement states which. Other financial years "
                       "are unaffected.",
        "sectors": ["manufacturer"],
    },
    "climate_var_dependence": {
        "frameworks": ["assetmgmt_tcfd", "sfdr_pai"],
        "default": "independent", "kind": "enum", "allowed": ["independent", "additive", "max"],
        "label": "Physical × transition loss dependence (combined VaR)",
        "description": "How physical and transition losses combine on a holding: 'independent' = "
                       "1−(1−physical)(1−transition); 'additive' = min(1, physical+transition), a conservative "
                       "stack; 'max' = the larger driver only.",
        "sectors": ["asset_manager"],
    },
    "resourcing_reallocation_cap_pct": {
        "frameworks": ["esrs_pack", "csrd_e1"],
        "default": 30, "kind": "int", "min": 5, "max": 100,
        "label": "Re-sourcing reallocation cap (%)",
        "description": "Maximum share of a commodity's spend assumed shiftable to a lower-risk origin near-term.",
        "sectors": ["manufacturer"],
    },
    "adaptation_scenario": {
        "frameworks": ["reit_tcfd", "reit_taxonomy"],
        "default": "reference", "kind": "enum", "allowed": ["conservative", "reference", "optimistic"],
        "label": "Adaptation effectiveness scenario",
        "description": "How much of the physical loss a resilience retrofit is assumed to avoid: conservative / "
                       "reference (EU Climate-ADAPT / IPCC AR6 WGII central) / optimistic.",
        "sectors": ["reit"],
    },
    # FX rate policy (multi-currency phase 2). BALANCES always convert at the closing rate of the book date (IAS 21
    # — not a switch); how yearly FLOWS convert is the institution's choice, stamped on every filing.
    "fx_flow_rate": {
        "frameworks": ["bank_tcfd", "bank_p3esg", "assetmgmt_tcfd", "sfdr_pai", "reit_tcfd", "reit_taxonomy",
                       "insurer_climate", "insurer_solvency", "esrs_pack", "csrd_e1"],
        "default": "period_average", "kind": "enum", "allowed": ["period_average", "closing"],
        "label": "Exchange rate for yearly figures (income, spend, revenue, premiums)",
        "description": "'period_average' = the average rate of the 12 months to the book date (IAS 21 practice — a "
                       "year's income at the year's rates); 'closing' = the book date's rate, like balances.",
    },
    "fx_client_rate_tolerance_pct": {
        "frameworks": ["bank_tcfd", "bank_p3esg", "assetmgmt_tcfd", "sfdr_pai", "reit_tcfd", "reit_taxonomy",
                       "insurer_climate", "insurer_solvency", "esrs_pack", "csrd_e1"],
        "default": 1.0, "kind": "float", "min": 0.1, "max": 10.0,
        "label": "Own exchange rates: allowed difference from the official rate (%)",
        "description": "Your own (treasury) rates are used when you supply them; one further than this from the ECB / "
                       "IMF rate for the same day needs a second person to accept it.",
    },
    "esg_energy_intensity_check_factor": {
        "frameworks": ["sfdr_pai", "assetmgmt_tcfd"],
        "default": 10.0, "kind": "float", "min": 2.0, "max": 1000.0,
        "label": "Company energy intensity: how far from the sector average before it is checked (×)",
        "description": "A reported energy intensity more than this many times above — or below — the sector average for "
                       "its activity is flagged as a possible unit slip (MWh typed as GWh is 1,000×) until someone "
                       "corrects it or confirms it with a reason. Ordinary differences are expected: set it wide.",
    },
    "equity_consolidation": {
        "frameworks": ["bank_tcfd", "bank_p3esg", "assetmgmt_tcfd", "reit_tcfd", "insurer_climate"],
        "default": "economic_share", "kind": "enum", "allowed": ["economic_share", "excluded", "full"],
        "label": "Equity-method consolidation treatment",
        "description": "How an equity-method associate's climate risk consolidates upward. 'economic_share' = "
                       "the parent's ownership share of the associate's book (the economic-exposure view); "
                       "'excluded' = not in the consolidated book (strict IFRS — an associate's assets aren't "
                       "line-by-line consolidated); 'full' = the whole book (only correct for a controlled sub).",
    },
    "retention_minimum_years": {
        "frameworks": ["bank_tcfd", "bank_p3esg", "assetmgmt_tcfd", "sfdr_pai", "reit_tcfd", "reit_taxonomy",
                       "insurer_climate", "insurer_solvency", "esrs_pack", "csrd_e1"],
        "default": 0, "kind": "int", "min": 0, "max": 50,
        "label": "Your own minimum record retention (years)",
        "description": "Filed reports are kept at least as long as the law requires for each one (shown on every filing, "
                       "with its legal source). Set a longer period here if your own policy requires it; it can never "
                       "shorten a legal period. Counted from the end of the year the filing was frozen.",
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
