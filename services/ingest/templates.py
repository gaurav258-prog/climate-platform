"""Upload templates for every sector, composed from the one field catalogue (services/ingest/fields.py).

A template lists which catalogue fields a sector's book carries, which are required, and any sector-specific
wording. The resolved field dicts carry everything the rest of intake needs (label, kind, vocabulary, aliases,
range), so validation, value matching, column profiling, the mapping editor and the template workbook all read the
same definition. To add a sector: list its fields here and register it in services/intake/catalog.py.
"""
from __future__ import annotations

from core import messages
from services.ingest.fields import FIELDS, VALIDATION_KIND, VOCABS, vocab_values

# A fixed list's values in customer words (the message catalogue's names): its own block, or the EUDR names it shares.
# A list whose values are already words (EPC ratings A–G) has none — the value is its own name.
VALUE_NAMES = {"eudr_movement": "eudr.kind", "eudr_role": "eudr.actor", "eudr_supplier_role": "eudr.actor"}
WORDS_ALREADY = {"epc_rating"}


def value_labels(vocab: str) -> dict[str, str] | None:
    """{value: customer name} for a fixed list; None where the values are already words."""
    if vocab in WORDS_ALREADY:
        return None
    block = messages.names()[VALUE_NAMES.get(vocab, f"onboarding.vocab.{vocab}")]
    return {v: block[v] for v in VOCABS[vocab].values}


def _template(*entries: tuple) -> list[dict]:
    """entries: (field name, required[, overrides]) → fully resolved field dicts."""
    out = []
    for e in entries:
        name, required = e[0], e[1]
        over = e[2] if len(e) > 2 else {}
        f = FIELDS[name]
        d = {"name": name, "required": required, "label": f.label, "kind": VALIDATION_KIND.get(f.kind, f.kind),
             "field_kind": f.kind, "description": f.description, "example": f.example, "aliases": list(f.aliases)}
        if f.vocab:
            d["vocab"] = f.vocab
            if not VOCABS[f.vocab].dynamic:
                d["allowed"] = list(VOCABS[f.vocab].values)
                d["value_labels"] = value_labels(f.vocab)
        if f.range:
            d["range"] = list(f.range)
        if f.kind == "money":
            d["flow"] = f.flow
            d["description"] = f.description + (" A yearly figure: converted at the average rate of the 12 months to the "
                                                "book date." if f.flow else "") + " In the file's currency (or its currency column)."
        d.update(over)
        out.append(d)
    return out


def _ref(what: str) -> dict:
    return {"description": f"Your own {what} id. When you send the book again, rows with the same ID update that asset "
                           "instead of adding a new one."}


ASSET_TEMPLATE_FIELDS = _template(
    ("asset_name", True), ("asset_type", True), ("latitude", True), ("longitude", True), ("appraised_value_eur", True),
    ("sector", True, {"description": "Sector / NACE classification.", "example": "Commercial real estate"}),
    ("counterparty_evic_eur", False, {"description": "Enterprise value including cash of a company that borrows (market cap + "
                                      "total debt + cash): required for a company — the denominator of its PCAF-attributed "
                                      "financed emissions. A household, a government or a central bank has none: leave it "
                                      "blank and say so in Counterparty sector."}),
    ("outstanding_loan_balance_eur", False), ("loan_origination_date", False), ("region", False), ("country", False),
    ("borrower_entity_id", False), ("minimum_safeguards_status", False), ("counterparty_govt_level", False),
    ("no_stated_maturity", False), ("counterparty_sector", False), ("immovable_collateral", False),
    ("building_value_eur", False, {"description": "The collateral building's own value, land excluded — the part a flood "
                                                  "or storm can damage. Without it, the flood loss on the loan's collateral "
                                                  "is reported as missing, with the reason (its appraised value includes the "
                                                  "land)."}),
    ("occupancy", False),
    ("external_ref", False, _ref("loan / facility")),
    ("currency", False), ("book_date", False), ("reporting_entity", False), ("intragroup_counterparty", False),
)

POLICY_TEMPLATE_FIELDS = _template(
    ("policy_name", True), ("latitude", True, {"example": "39.4699"}), ("longitude", True, {"example": "-0.3763"}),
    ("building_value_eur", False, {"description": "Part of the total insured value. Give it with the contents and business "
                                                  "interruption values, or give the sum insured instead."}),
    ("contents_value_eur", False), ("business_interruption_value_eur", False), ("sum_insured_eur", False),
    ("construction_type", False), ("year_built", False), ("number_of_stories", False), ("deductible_pct", False),
    ("occupancy", False),
    ("region", False, {"example": "Valencia"}), ("country", False, {"example": "ES"}), ("postal_code", False, {"example": "46001"}),
    ("motor_sum_insured_eur", False), ("policy_type", False), ("external_ref", False, _ref("policy or location")),
    ("currency", False), ("book_date", False), ("reporting_entity", False), ("intragroup_counterparty", False),
)

PROPERTY_TEMPLATE_FIELDS = _template(
    ("property_name", True), ("latitude", True, {"example": "51.9244"}), ("longitude", True, {"example": "4.4777"}),
    ("property_value_eur", True), ("annual_noi_eur", True), ("annual_gross_rental_revenue_eur", False),
    ("sum_insured_eur", False, {"description": "The property's insured value (buildings sum insured) — the base of what "
                                              "its insurance costs; never assumed equal to its market value."}),
    ("building_value_eur", False, {"description": "The building's own value, land excluded — the part a flood or storm "
                                                  "can damage. Without it, the flood loss is reported as missing, with the "
                                                  "reason (the property value includes the land).", "example": "8000000"}),
    ("occupancy", False),
    ("property_type", True), ("construction_type", False), ("year_built", False, {"example": "2011"}),
    ("number_of_stories", False, {"example": "1"}), ("region", False, {"example": "South Holland"}),
    ("country", False, {"example": "NL"}), ("epc_rating", False), ("borrower_entity_id", False),
    ("minimum_safeguards_status", False), ("ped_top15_evidence", False), ("meets_new_building_criteria", False),
    ("heating_rated_output_kw", False), ("energy_performance_monitoring", False), ("adaptation_plan_in_place", False),
    ("external_ref", False, _ref("property")),
    ("currency", False), ("book_date", False), ("reporting_entity", False), ("intragroup_counterparty", False),
)

HOLDING_TEMPLATE_FIELDS = _template(
    ("holding_name", True), ("latitude", True, {"description": "Decimal degrees (HQ or primary asset location).", "example": "59.3293"}),
    ("longitude", True, {"example": "18.0686"}), ("position_value_eur", True), ("sector", True), ("nace_code", False),
    ("region", False, {"example": "Stockholm"}), ("country", False, {"example": "SE"}), ("borrower_entity_id", False),
    ("minimum_safeguards_status", False), ("external_ref", False, _ref("holding / position")),
    ("currency", False), ("book_date", False), ("reporting_entity", False), ("intragroup_counterparty", False),
)

PLOT_TEMPLATE_FIELDS = _template(
    ("plot_name", True),
    ("latitude", True, {"description": "Decimal degrees, to 6 decimal places (the plot's EUDR point). Leave blank if you give "
                                       "the plot boundary.", "example": "6.694400"}),
    ("longitude", True, {"description": "Decimal degrees, to 6 decimal places. Leave blank if you give the plot boundary.",
                         "example": "-1.605500"}),
    ("commodity", True), ("annual_spend_eur", True), ("plot_geojson", False), ("plot_area_ha", False),
    ("region", False, {"example": "Ashanti"}), ("country", False, {"example": "GH"}), ("irrigation_status", False),
    ("postal_address", False),
    ("external_ref", False, _ref("plot or farm")), ("held_from", False), ("held_until", False), ("reporting_entity", False),
    ("supplier_ref", False),
    ("currency", False), ("book_date", False),
)

SITE_TEMPLATE_FIELDS = _template(
    ("site_name", True),
    ("latitude", True, {"description": "Decimal degrees. Leave blank if you give the address.", "example": "39.4699"}),
    ("longitude", True, {"description": "Decimal degrees. Leave blank if you give the address.", "example": "-0.3763"}),
    ("address", False), ("site_type", False), ("occupancy", False), ("country", False, {"example": "ES"}),
    ("region", False, {"example": "Valencia"}), ("annual_value_eur", False), ("annual_throughput_eur", False), ("site_area_ha", False),
    ("held_from", False), ("held_until", False), ("external_ref", False, _ref("site")), ("reporting_entity", False),
    ("currency", False), ("book_date", False),
)

SITE_YEAR_END_TEMPLATE_FIELDS = _template(
    ("site_ref", True),
    ("book_date", True, {"label": "Period end", "description": "The last day of the financial year the figures are for "
                         "(YYYY-MM-DD). The carrying amount converts at that day's closing rate, net revenue at the average "
                         "of the year to it.", "example": "2025-12-31"}),
    ("carrying_amount_eur", False), ("carrying_amount_adapted_eur", False), ("net_revenue_eur", False), ("currency", False),
)

# EUDR (Regulation (EU) 2023/1115): the parties (Art. 5(3), 9(1)(e)-(f)), each placing on the market / making available /
# export (Annex II points 1-3, Art. 9(1)(a)-(f)) and the plots each came from with the production dates (Art. 9(1)(d))
# the banking book's counterparties: one row per counterparty, its id as the loan tape states it; the date of the
# balance sheet the total liabilities are taken from is the row's book date (the amount converts at that day's rate)
BANK_COUNTERPARTY_TEMPLATE_FIELDS = _template(
    ("counterparty_ref", True), ("counterparty_name", False), ("total_liabilities_eur", False),
    ("counterparty_revenue_eur", False), ("currency", False),
    ("book_date", False, {"label": "Financial year end", "description": "The end of the counterparty's financial year the "
                          "figures are taken from (YYYY-MM-DD) — required with them: the total liabilities are its balance "
                          "sheet on that day (closing rate), the revenue is for the year ending on it (average rate of the "
                          "year)."}),
)

FUND_TEMPLATE_FIELDS = _template(
    ("fund_name", True), ("fund_type", True), ("sfdr_classification", True), ("base_currency", True), ("parent_fund", False),
    ("fund_lei", False),
)
FUND_HOLDING_TEMPLATE_FIELDS = _template(
    ("fund_name", True), ("isin", True), ("market_value_eur", True), ("currency", False),
    ("book_date", True, {"label": "As-of date", "description": "The date of the fund's book this position is in "
                         "(YYYY-MM-DD). A value in another currency converts to EUR at that day's closing rate."}),
    ("asset_class", False),
)

ISSUER_FIGURE_TEMPLATE_FIELDS = _template(
    ("isin", True, {"description": "The ISIN of a security of the company you hold (12 characters, ISO 6166)."}),
    ("book_date", True, {"label": "Financial year end", "description": "The end of the company's financial year the "
                         "figures are for (YYYY-MM-DD): its revenue converts at the average rate of that year, its EVIC "
                         "and physical asset value at that day's closing rate."}),
    ("currency", False, {"description": "ISO 4217 code of this row's amounts (e.g. USD) — the currency of the company's "
                         "accounts. Overrides the currency declared for the file."}),
    ("revenue_eur", False), ("evic_eur", False), ("physical_asset_value_eur", False), ("scope1_tco2e", False),
    ("scope2_tco2e", False), ("scope3_tco2e", False), ("nace_code", False), ("energy_consumption_gwh", False),
    ("non_renewable_consumption_pct", False), ("non_renewable_production_pct", False), ("biodiversity_sensitive_ops", False),
    ("emissions_to_water_tonnes", False), ("hazardous_waste_tonnes", False), ("ungc_oecd_violation", False),
    ("ungc_oecd_no_monitoring", False), ("gender_pay_gap_pct", False), ("board_female_pct", False),
    ("controversial_weapons", False), ("taxonomy_eligible_pct", False), ("taxonomy_aligned_pct", False),
    ("taxonomy_aligned_capex_pct", False), ("taxonomy_fossil_gas_aligned_pct", False), ("taxonomy_nuclear_aligned_pct", False),
    ("taxonomy_fossil_gas_aligned_capex_pct", False), ("taxonomy_nuclear_aligned_capex_pct", False),
    ("taxonomy_dnsh_ok", False), ("taxonomy_min_safeguards_ok", False),
)

EUDR_SUPPLIER_TEMPLATE_FIELDS = _template(
    ("party_name", True), ("party_ref", True), ("address", True, {"description": "Postal address (Art. 9(1)(e))."}),
    ("contact_email", True), ("trade_name", False), ("web_address", False), ("country", False),
)
EUDR_CUSTOMER_TEMPLATE_FIELDS = _template(
    ("party_name", True), ("party_ref", True), ("address", True, {"description": "Postal address (Art. 9(1)(f))."}),
    ("contact_email", True), ("trade_name", False), ("web_address", False), ("country", False),
)
EUDR_MOVEMENT_TEMPLATE_FIELDS = _template(
    ("movement_ref", True), ("movement_kind", True), ("actor_role", True), ("planned_on", True), ("hs_code", True),
    ("description", True), ("customs_flow", True), ("trade_name", False), ("scientific_names", False),
    ("net_mass_kg", False), ("mass_deviation_pct", False), ("supplementary_unit", False), ("supplementary_qty", False),
    ("volume_m3", False), ("items_count", False), ("supplier_ref", False), ("supplier_role", False), ("customer_ref", False), ("upstream_refs", False),
    ("reporting_entity", False),
)
EUDR_MOVEMENT_PLOT_TEMPLATE_FIELDS = _template(
    ("movement_ref", True), ("plot_ref", True), ("production_from", True), ("production_to", True),
)

# value sets used by the sector rules — the same vocabularies the checks use
CONSTRUCTION_TYPES = vocab_values("construction_type")
EPC_RATINGS = vocab_values("epc_rating")
SAFEGUARDS_STATUSES = vocab_values("safeguards_status")
IRRIGATION_VALUES = vocab_values("irrigation")
GOVT_LEVELS = vocab_values("govt_level")
