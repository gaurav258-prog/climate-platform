"""Upload templates for every sector: the columns a customer file must/may carry, and the value vocabularies.

One definition per sector, read by the upload routes, the template workbooks, the intake controls and the
sector ingestion code alike, so a column means the same thing everywhere.
"""
from __future__ import annotations

ASSET_TEMPLATE_FIELDS = [
    {"name": "asset_name", "required": True, "label": "Asset name", "kind": "text", "description": "Free-text asset/property name.", "example": "Frankfurt Tower 1"},
    {"name": "asset_type", "required": True, "label": "Asset type", "kind": "text", "description": "Property/collateral type.", "example": "commercial_real_estate"},
    {"name": "latitude", "required": True, "label": "Latitude", "kind": "lat", "description": "Decimal degrees.", "example": "50.1109"},
    {"name": "longitude", "required": True, "label": "Longitude", "kind": "lon", "description": "Decimal degrees.", "example": "8.6821"},
    {"name": "appraised_value_eur", "required": True, "label": "Appraised value (EUR)", "kind": "money", "description": "Current appraised/collateral value.", "example": "12000000"},
    {"name": "sector", "required": True, "label": "Sector", "kind": "text", "description": "Sector / NACE classification.", "example": "Commercial real estate"},
    {"name": "counterparty_evic_eur", "required": True, "label": "Counterparty EVIC (EUR)", "kind": "money",
     "description": "Enterprise Value Including Cash of the borrowing counterparty (market cap + total debt + cash; the latest reported or credibly estimated figure). Required for PCAF-attributed financed emissions.",
     "example": "185000000"},
    {"name": "outstanding_loan_balance_eur", "required": False, "label": "Outstanding loan balance (EUR)", "kind": "money", "description": "Current outstanding principal — enables LTV.", "example": "8400000"},
    {"name": "loan_origination_date", "required": False, "label": "Loan origination date", "kind": "date", "description": "YYYY-MM-DD.", "example": "2022-03-01"},
    {"name": "region", "required": False, "label": "Region", "kind": "text", "description": "Free-text region/city.", "example": "Frankfurt"},
    {"name": "country", "required": False, "label": "Country", "kind": "iso2", "description": "ISO-2 country code.", "example": "DE"},
    {"name": "borrower_entity_id", "required": False, "label": "Borrower ID (LEI)", "kind": "text", "description": "Borrower's LEI or other stable entity ID — "
     "lets a minimum-safeguards compliance flag be matched/refreshed by entity rather than re-collected per loan.", "example": "5493001KJTIIGC8Y1R12"},
    {"name": "minimum_safeguards_status", "required": False, "label": "Minimum-safeguards status", "kind": "text", "description": "compliant / non_compliant, from your own "
     "OECD/UN/ILO counterparty screening — enables a real EU Taxonomy minimum-safeguards check (also requires a "
     "nace_code on the loan, which today's upload doesn't yet collect — see the taxonomy_status note below).", "example": "compliant"},
    {"name": "counterparty_govt_level", "required": False, "label": "Counterparty government level", "kind": "enum", "allowed": ["central", "regional", "local"],
     "description": "Required to correctly scope EU Taxonomy Art. 7(1)'s central-government exclusion — leave blank for non-government counterparties.", "example": "central"},
    {"name": "no_stated_maturity", "required": False, "label": "No stated maturity", "kind": "boolean",
     "description": "True for an exposure with no stated maturity BY ITS NATURE — an equity holding, a perpetual "
     "instrument, or similar (NOT simply a loan whose maturity you haven't supplied yet). Per EBA Q&A 2022_6515, "
     "these are disclosed in the largest ('>20 years') Pillar 3 maturity bucket rather than left uncounted.",
     "example": "true"},
    {"name": "external_ref", "required": False, "label": "Your asset ID", "kind": "text",
     "description": "Your own loan / facility id. When you send the book again, rows with the same ID update that asset instead of adding a new one.", "example": "REF-000123"},
]

POLICY_TEMPLATE_FIELDS = [
    {"name": "policy_name", "required": True, "description": "Free-text location/policy name.", "example": "Valencia Warehouse 12"},
    {"name": "latitude", "required": True, "description": "Decimal degrees.", "example": "39.4699"},
    {"name": "longitude", "required": True, "description": "Decimal degrees.", "example": "-0.3763"},
    {"name": "building_value_eur", "required": False, "description": "TIV component. Provide this + contents + BI, OR sum_insured_eur directly.", "example": "3000000"},
    {"name": "contents_value_eur", "required": False, "description": "TIV component (business personal property).", "example": "500000"},
    {"name": "business_interruption_value_eur", "required": False, "description": "TIV component (business income).", "example": "200000"},
    {"name": "sum_insured_eur", "required": False, "description": "Total Insured Value, if not broken into components above.", "example": "3700000"},
    {"name": "construction_type", "required": False, "description": "ISO Construction Class: frame / joisted_masonry / non_combustible / masonry_non_combustible / fire_resistive.", "example": "masonry_non_combustible"},
    {"name": "year_built", "required": False, "kind": "int", "description": "Year of construction.", "example": "1998"},
    {"name": "number_of_stories", "required": False, "kind": "int", "description": "Number of stories.", "example": "3"},
    {"name": "deductible_pct", "required": False, "description": "Policy deductible, as a fraction (0.02 = 2%).", "example": "0.02"},
    {"name": "region", "required": False, "description": "Free-text region.", "example": "Valencia"},
    {"name": "country", "required": False, "description": "ISO-2 country code.", "example": "ES"},
    {"name": "cresta_zone", "required": False, "kind": "int", "description": "EIOPA/CRESTA risk-zone number for this location (Del. Reg. 2015/35 Annex IX). Enables the exact standard-formula zonal SCR; leave blank for the country-level approximation.", "example": "21"},
    {"name": "motor_sum_insured_eur", "required": False, "description": "Motor-vehicle sum insured at this location (Art. 123(7)/124(7)), added into the flood/hail standard-formula SCR at 1.5x/5x. Leave blank for a pure property book.", "example": "150000"},
    {"name": "external_ref", "required": False, "label": "Your asset ID", "kind": "text",
     "description": "Your own policy or location id. When you send the book again, rows with the same ID update that asset instead of adding a new one.", "example": "REF-000123"},
]

CONSTRUCTION_TYPES = {"frame", "joisted_masonry", "non_combustible", "masonry_non_combustible", "fire_resistive"}
PROPERTY_TEMPLATE_FIELDS = [
    {"name": "property_name", "required": True, "description": "Free-text property name.", "example": "Rotterdam Logistics Park 4"},
    {"name": "latitude", "required": True, "description": "Decimal degrees.", "example": "51.9244"},
    {"name": "longitude", "required": True, "description": "Decimal degrees.", "example": "4.4777"},
    {"name": "property_value_eur", "required": True, "description": "Current market/appraised value.", "example": "42000000"},
    {"name": "annual_noi_eur", "required": True, "description": "Annual net operating income.", "example": "2400000"},
    {"name": "annual_gross_rental_revenue_eur", "required": False, "description": "Annual GROSS rental revenue "
     "before operating expenses (Del. Reg. (EU) 2021/2178 Annex I §1.1.1 turnover-KPI basis) — enables the real "
     "EU Taxonomy Turnover KPI instead of the NOI-as-proxy fallback.", "example": "3600000"},
    {"name": "property_type", "required": True, "description": "office / retail / logistics / light_industrial / multifamily.", "example": "logistics"},
    {"name": "construction_type", "required": False, "description": "ISO Construction Class: frame / joisted_masonry / non_combustible / masonry_non_combustible / fire_resistive.", "example": "non_combustible"},
    {"name": "year_built", "required": False, "kind": "int", "description": "Year of construction.", "example": "2011"},
    {"name": "number_of_stories", "required": False, "kind": "int", "description": "Number of stories.", "example": "1"},
    {"name": "region", "required": False, "description": "Free-text region.", "example": "South Holland"},
    {"name": "country", "required": False, "description": "ISO-2 country code.", "example": "NL"},
    {"name": "epc_rating", "required": False, "description": "Building Energy Performance Certificate grade (A-G) — "
     "enables a real EU Taxonomy substantial-contribution check instead of an unverified gap.", "example": "B"},
    {"name": "borrower_entity_id", "required": False, "description": "Owning entity's LEI or other stable ID — "
     "lets a minimum-safeguards compliance flag be matched/refreshed by entity rather than re-collected per property.", "example": "5493001KJTIIGC8Y1R12"},
    {"name": "minimum_safeguards_status", "required": False, "description": "compliant / non_compliant, from your own "
     "OECD/UN/ILO counterparty screening — enables a real EU Taxonomy minimum-safeguards check.", "example": "compliant"},
    {"name": "external_ref", "required": False, "label": "Your asset ID", "kind": "text",
     "description": "Your own property id. When you send the book again, rows with the same ID update that asset instead of adding a new one.", "example": "REF-000123"},
]

EPC_RATINGS = {"A", "B", "C", "D", "E", "F", "G"}
SAFEGUARDS_STATUSES = {"compliant", "non_compliant"}
HOLDING_TEMPLATE_FIELDS = [
    {"name": "holding_name", "required": True, "description": "Company / security name.", "example": "Nordisk Logistics Properties AB"},
    {"name": "latitude", "required": True, "description": "Decimal degrees (HQ or primary asset location).", "example": "59.3293"},
    {"name": "longitude", "required": True, "description": "Decimal degrees.", "example": "18.0686"},
    {"name": "position_value_eur", "required": True, "description": "Market value of the position.", "example": "18500000"},
    {"name": "sector", "required": True, "description": "Free-text sector / industry.", "example": "Real estate"},
    {"name": "nace_code", "required": False, "description": "NACE code, if known — enables real EU Taxonomy classification.", "example": "68.20"},
    {"name": "region", "required": False, "description": "Free-text region.", "example": "Stockholm"},
    {"name": "country", "required": False, "description": "ISO-2 country code.", "example": "SE"},
    {"name": "borrower_entity_id", "required": False, "description": "Holding's LEI or other stable entity ID — "
     "lets a minimum-safeguards compliance flag be matched/refreshed by entity rather than re-collected per row.", "example": "5493001KJTIIGC8Y1R12"},
    {"name": "minimum_safeguards_status", "required": False, "description": "compliant / non_compliant, from your own "
     "OECD/UN/ILO counterparty screening — enables a real EU Taxonomy minimum-safeguards check.", "example": "compliant"},
    {"name": "external_ref", "required": False, "label": "Your asset ID", "kind": "text",
     "description": "Your own holding / position id. When you send the book again, rows with the same ID update that asset instead of adding a new one.", "example": "REF-000123"},
]

PLOT_TEMPLATE_FIELDS = [
    {"name": "plot_name", "required": True, "description": "Free-text plot/farm name.", "example": "Ashanti Plot 4"},
    {"name": "latitude", "required": True, "description": "Decimal degrees, 6 d.p. (EUDR point geolocation). Leave blank if you supply plot_geojson — we take the centroid.", "example": "6.694400"},
    {"name": "longitude", "required": True, "description": "Decimal degrees, 6 d.p. Leave blank if you supply plot_geojson.", "example": "-1.605500"},
    {"name": "commodity", "required": True, "description": "Must match a commodity already on this platform (e.g. Cocoa, Coffee, Citrus).", "example": "Cocoa"},
    {"name": "annual_spend_eur", "required": True, "description": "Annual procurement spend sourced from this plot.", "example": "150000"},
    {"name": "plot_geojson", "required": False, "description": "EUDR plot BOUNDARY as a GeoJSON Polygon — REQUIRED for any plot over 4 ha (a point is only valid at/below 4 ha). Area is computed from it.", "example": '{"type":"Polygon","coordinates":[[[-1.606,6.694],[-1.604,6.694],[-1.604,6.696],[-1.606,6.696],[-1.606,6.694]]]}'},
    {"name": "plot_area_ha", "required": False, "description": "Plot area in hectares. Auto-computed (geodesic) when plot_geojson is given; only needed for a point-only plot.", "example": "2.3"},
    {"name": "region", "required": False, "description": "Free-text region.", "example": "Ashanti"},
    {"name": "country", "required": False, "description": "ISO-2 country code.", "example": "GH"},
    {"name": "irrigation_status", "required": False, "description": "irrigated / rain_fed / mixed. Declared, "
     "not modelled: an irrigated plot's drought score is shown as an upper bound; the crop € is unchanged "
     "(it reflects the origin's national irrigated/rain-fed mix).", "example": "irrigated"},
    {"name": "external_ref", "required": False, "label": "Your asset ID", "kind": "text",
     "description": "Your own plot or farm id. When you send the book again, rows with the same ID update that asset instead of adding a new one.", "example": "REF-000123"},
]

IRRIGATION_VALUES = {"irrigated", "rain_fed", "mixed"}
