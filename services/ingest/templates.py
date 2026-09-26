"""Upload templates for every sector, composed from the one field catalogue (services/ingest/fields.py).

A template lists which catalogue fields a sector's book carries, which are required, and any sector-specific
wording. The resolved field dicts carry everything the rest of intake needs (label, kind, vocabulary, aliases,
range), so validation, value matching, column profiling, the mapping editor and the template workbook all read the
same definition. To add a sector: list its fields here and register it in services/intake/catalog.py.
"""
from __future__ import annotations

from services.ingest.fields import FIELDS, VALIDATION_KIND, VOCABS, vocab_values


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
    ("counterparty_evic_eur", True, {"description": "Enterprise Value Including Cash of the borrowing counterparty (market cap + "
                                     "total debt + cash). Required for PCAF-attributed financed emissions."}),
    ("outstanding_loan_balance_eur", False), ("loan_origination_date", False), ("region", False), ("country", False),
    ("borrower_entity_id", False), ("minimum_safeguards_status", False), ("counterparty_govt_level", False),
    ("no_stated_maturity", False), ("external_ref", False, _ref("loan / facility")),
    ("currency", False), ("book_date", False),
)

POLICY_TEMPLATE_FIELDS = _template(
    ("policy_name", True), ("latitude", True, {"example": "39.4699"}), ("longitude", True, {"example": "-0.3763"}),
    ("building_value_eur", False, {"description": "TIV component. Provide this + contents + BI, OR sum_insured_eur directly."}),
    ("contents_value_eur", False), ("business_interruption_value_eur", False), ("sum_insured_eur", False),
    ("construction_type", False), ("year_built", False), ("number_of_stories", False), ("deductible_pct", False),
    ("region", False, {"example": "Valencia"}), ("country", False, {"example": "ES"}), ("cresta_zone", False),
    ("motor_sum_insured_eur", False), ("policy_type", False), ("external_ref", False, _ref("policy or location")),
    ("currency", False), ("book_date", False),
)

PROPERTY_TEMPLATE_FIELDS = _template(
    ("property_name", True), ("latitude", True, {"example": "51.9244"}), ("longitude", True, {"example": "4.4777"}),
    ("property_value_eur", True), ("annual_noi_eur", True), ("annual_gross_rental_revenue_eur", False),
    ("property_type", True), ("construction_type", False), ("year_built", False, {"example": "2011"}),
    ("number_of_stories", False, {"example": "1"}), ("region", False, {"example": "South Holland"}),
    ("country", False, {"example": "NL"}), ("epc_rating", False), ("borrower_entity_id", False),
    ("minimum_safeguards_status", False), ("external_ref", False, _ref("property")),
    ("currency", False), ("book_date", False),
)

HOLDING_TEMPLATE_FIELDS = _template(
    ("holding_name", True), ("latitude", True, {"description": "Decimal degrees (HQ or primary asset location).", "example": "59.3293"}),
    ("longitude", True, {"example": "18.0686"}), ("position_value_eur", True), ("sector", True), ("nace_code", False),
    ("region", False, {"example": "Stockholm"}), ("country", False, {"example": "SE"}), ("borrower_entity_id", False),
    ("minimum_safeguards_status", False), ("external_ref", False, _ref("holding / position")),
    ("currency", False), ("book_date", False),
)

PLOT_TEMPLATE_FIELDS = _template(
    ("plot_name", True),
    ("latitude", True, {"description": "Decimal degrees, 6 d.p. (EUDR point). Leave blank if you give plot_geojson.", "example": "6.694400"}),
    ("longitude", True, {"description": "Decimal degrees, 6 d.p. Leave blank if you give plot_geojson.", "example": "-1.605500"}),
    ("commodity", True), ("annual_spend_eur", True), ("plot_geojson", False), ("plot_area_ha", False),
    ("region", False, {"example": "Ashanti"}), ("country", False, {"example": "GH"}), ("irrigation_status", False),
    ("external_ref", False, _ref("plot or farm")),
    ("currency", False), ("book_date", False),
)

# value sets used by the sector rules — the same vocabularies the checks use
CONSTRUCTION_TYPES = vocab_values("construction_type")
EPC_RATINGS = vocab_values("epc_rating")
SAFEGUARDS_STATUSES = vocab_values("safeguards_status")
IRRIGATION_VALUES = vocab_values("irrigation")
GOVT_LEVELS = vocab_values("govt_level")
