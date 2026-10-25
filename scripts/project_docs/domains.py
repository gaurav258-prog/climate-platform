"""The domains docs/BACKEND_SCHEMA.md groups tables into — a declared grouping (the database does not record one).

Each table belongs to exactly one domain: the first whose patterns match its name (shell-style, `fnmatch`). A table no
pattern matches stops the generator, naming the table — add it to the domain it serves.
"""
from __future__ import annotations

from fnmatch import fnmatchcase

DOMAINS: list[tuple[str, str, list[str]]] = [
    ("identity", "Identity & access", [
        "users", "roles", "permissions", "role_permissions", "user_roles", "api_keys", "refresh_token",
        "password_reset", "user_activation", "mfa_backup_code", "webauthn_*", "saml_assertion_seen",
        "tenant_sso_config", "scim_*", "access_audit_log"]),
    ("tenants", "Tenants, onboarding & commercial", [
        "organizations", "org_entitlements", "org_module_subscriptions", "client_intake*", "customer_contract",
        "subscription", "invoice", "esign_request", "service_request*", "public_lookups"]),
    ("scores", "Golden score layer & hazard data", [
        "canonical_scores", "climate_risk_scores", "satellite_observations", "climatology_baseline",
        "frost_baseline", "soil_moisture_baseline", "protected_*", "ml_features_*", "coastal_*", "glacial_lake_cell",
        "terrain_cell", "aqueduct_*", "hazard_relevance", "station_extremes", "tide_gauge_extremes"]),
    ("events", "Hazard events & zones", [
        "seismic_events", "storm_events", "volcanic_events", "volcanic_hazard_zones", "damage_assessments"]),
    ("models", "Models & validation", [
        "model_*", "validation_*", "forecast_verification", "engine_runs", "outcome_feedback", "climate_scenarios"]),
    ("loss", "Loss engine", [
        "hazard_intensity_samples", "flood_protection_samples", "loss_*", "asset_building_matches"]),
    ("books", "Financial books (bank, insurer, real estate, portfolio)", [
        "bank_assets", "bank_asset_valuations", "bank_counterparties", "bank_building_energy", "insurance_*", "insurer_incurred_losses",
        "parametric_contracts", "trigger_events", "realestate_*", "portfolio_entit*", "ext_*",
        "climate_hazard_exposure", "loan_arrears", "gl_balance", "customer_locations", "asset_observations",
        "asset_conflicts", "site_period_values", "third_party", "scenario_financial_impact"]),
    ("assetmgmt", "Asset management (issuers, securities, funds)", [
        "issuer*", "securities", "fund_*", "funds", "assetmgmt_*", "reference_resolution_log", "sfdr_batch_*",
        "eet_publications", "org_eet_answers"]),
    ("eudr", "EUDR", ["eudr_*", "sc_eudr_dds"]),
    ("agri", "Agri-food supply chain & crops", ["sc_*", "crop_*", "commodity_price_index"]),
    ("filings", "Regulatory reporting & filings", [
        "regulatory_filing*", "report_snapshots", "filing_*", "org_channel_credential", "template_answers",
        "provided_datapoint", "reported_*", "reporting_entities", "entity_structure_*", "csrd_reporting_role",
        "ghg_emissions_inventory", "regulatory_packages", "regulatory_obligation", "org_reporting_settings*",
        "org_regulatory_attribute", "assurance_share*", "regulatory_audit_log", "kpi_summary",
        "bank_disclosure_submissions", "reporting_period_close"]),
    ("regchange", "Regulatory change monitoring (CRCS)", [
        "reg_act_relation", "reg_alert", "reg_detected_change", "reg_early_signal", "reg_source_snapshot",
        "regulatory_change", "regspec_signoff"]),
    ("supervision", "Supervision", ["supervision_*", "supervisor_*", "reg_submission_case", "reg_case_message"]),
    ("workflow", "Workflow, decisions & controls", [
        "regulatory_task*", "approval_*", "risk_decision", "decision_*", "kri_*", "control_*",
        "governance_structure", "board_pack*", "notifiable_event", "alert_*", "analytics_saved_view"]),
    ("intake", "Data intake & integration", [
        "ingest_*", "intake_*", "source_systems", "entity_source_refs", "feed_refresh_log", "webhook_*",
        "email_outbox", "job_runs", "worker_heartbeat"]),
    ("reference", "Reference data, FX, settings & audit", [
        "ref_*", "fx_*", "geocode_cache", "org_calc_settings*", "audit_log", "alembic_version",
        "migration_meta.applied_file"]),
]


class UnassignedTable(LookupError):
    """A table no domain pattern matches."""


def domain_of(qualified: str) -> str:
    """The key of the domain a table belongs to; `qualified` is schema.table (public tables match on the name)."""
    schema, _, name = qualified.partition(".")
    for key, _title, patterns in DOMAINS:
        for p in patterns:
            if fnmatchcase(qualified if "." in p else name, p) and (schema == "public" or "." in p):
                return key
    raise UnassignedTable(f"table {qualified} is in no domain — add it to DOMAINS in scripts/project_docs/domains.py")


TITLES = {key: title for key, title, _ in DOMAINS}
