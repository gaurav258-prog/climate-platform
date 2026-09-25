"""The field catalogue: every field a customer file can carry, defined ONCE, for every sector.

A field says what it is (kind), what values it may take (vocabulary), what customers tend to call it (aliases), and
what counts as plausible (range). Sector templates (templates.py) are compositions of these fields. Everything that
reads a customer file works from this catalogue — validation, value matching, column profiling, the mapping editor,
the template workbook — so adding a sector means listing its fields, nothing else.

Vocabulary synonyms are EXACT equivalences only (ISO construction class numbers, spelling variants). A value that
is merely similar ("Concrete") is never mapped here; the customer maps it, and the mapping is recorded.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


def norm_token(v) -> str:
    """Case, spacing and separator-insensitive form: 'Joisted Masonry' / 'joisted-masonry' → 'joisted_masonry'."""
    return re.sub(r"[\s\-/.]+", "_", str(v).strip().lower()).strip("_")


@dataclass(frozen=True)
class Vocab:
    values: tuple[str, ...]
    synonyms: dict = field(default_factory=dict)     # norm_token(their value) → our value (exact equivalences)
    dynamic: bool = False                            # values come from the database (resolved per organisation)

    def lookup(self) -> dict[str, str]:
        out = {norm_token(v): v for v in self.values}
        out.update(self.synonyms)
        return out


VOCABS: dict[str, Vocab] = {
    # ISO construction classes. The ISO class numbers are exact; class 5 (modified fire resistive) has no equivalent
    # in our set and is deliberately NOT mapped.
    "construction_type": Vocab(("frame", "joisted_masonry", "non_combustible", "masonry_non_combustible", "fire_resistive"),
                               {"1": "frame", "iso_1": "frame", "class_1": "frame", "wood_frame": "frame", "timber_frame": "frame",
                                "2": "joisted_masonry", "iso_2": "joisted_masonry", "class_2": "joisted_masonry",
                                "3": "non_combustible", "iso_3": "non_combustible", "class_3": "non_combustible",
                                "noncombustible": "non_combustible",
                                "4": "masonry_non_combustible", "iso_4": "masonry_non_combustible", "class_4": "masonry_non_combustible",
                                "masonry_noncombustible": "masonry_non_combustible",
                                "6": "fire_resistive", "iso_6": "fire_resistive", "class_6": "fire_resistive",
                                "fire_resistant": "fire_resistive"}),
    "epc_rating": Vocab(("A", "B", "C", "D", "E", "F", "G")),
    "safeguards_status": Vocab(("compliant", "non_compliant"),
                               {"noncompliant": "non_compliant", "not_compliant": "non_compliant"}),
    "govt_level": Vocab(("central", "regional", "local")),
    "irrigation": Vocab(("irrigated", "rain_fed", "mixed"), {"rainfed": "rain_fed"}),
    "commodity": Vocab((), dynamic=True),            # the commodities on this platform (sc_commodities)
    "boolean": Vocab(("true", "false"), {"yes": "true", "y": "true", "1": "true", "no": "false", "n": "false", "0": "false"}),
}


@dataclass(frozen=True)
class FieldDef:
    name: str
    label: str
    kind: str                        # text | name | id | lat | lon | money | int | fraction | date | iso2 | vocab | geojson
    description: str
    example: str
    vocab: Optional[str] = None
    aliases: tuple[str, ...] = ()
    range: Optional[tuple[float, float]] = None


def _f(name, label, kind, description, example, vocab=None, aliases=(), range=None) -> FieldDef:  # noqa: A002
    return FieldDef(name, label, kind, description, example, vocab, tuple(aliases), range)


_REF = "Your own {what} id. When you send the book again, rows with the same ID update that asset instead of adding a new one."

FIELDS: dict[str, FieldDef] = {f.name: f for f in (
    # identity & location — shared by every sector
    _f("external_ref", "Your asset ID", "id", _REF.format(what="asset"), "REF-000123",
       aliases=("id", "asset_id", "loan_id", "facility_id", "policy_id", "location_id", "property_id", "holding_id",
                "position_id", "plot_id", "farm_id", "reference", "ref", "your_asset_id", "account_number")),
    _f("latitude", "Latitude", "lat", "Decimal degrees.", "50.1109", aliases=("lat", "y", "latitude_dd", "gps_lat", "gps_n", "north", "n", "lat_dd", "breitengrad")),
    _f("longitude", "Longitude", "lon", "Decimal degrees.", "8.6821", aliases=("lon", "lng", "long", "x", "longitude_dd", "gps_lon", "gps_long", "gps_e", "east", "e", "lon_dd", "laengengrad")),
    _f("region", "Region", "text", "Free-text region / city.", "Frankfurt", aliases=("city", "state", "province", "area", "location")),
    _f("country", "Country", "iso2", "ISO-2 country code.", "DE", aliases=("country_code", "iso2", "ctry", "cntry")),
    # names
    _f("asset_name", "Asset name", "name", "Free-text asset / collateral name.", "Frankfurt Tower 1",
       aliases=("name", "asset", "collateral", "collateral_name", "borrower", "borrower_name", "property")),
    _f("policy_name", "Location / policy name", "name", "Free-text location / policy name.", "Valencia Warehouse 12",
       aliases=("name", "location_name", "site_name", "risk_name", "insured_location", "location")),
    _f("property_name", "Property name", "name", "Free-text property name.", "Rotterdam Logistics Park 4",
       aliases=("name", "property", "building", "asset_name", "building_name")),
    _f("holding_name", "Holding name", "name", "Company / security name.", "Nordisk Logistics Properties AB",
       aliases=("name", "issuer", "issuer_name", "security_name", "company", "company_name")),
    _f("plot_name", "Plot name", "name", "Free-text plot / farm name.", "Ashanti Plot 4", aliases=("name", "farm", "farm_name", "plot")),
    # classification
    _f("asset_type", "Asset type", "text", "Property / collateral type.", "commercial_real_estate", aliases=("type", "collateral_type", "property_type")),
    _f("property_type", "Property type", "text", "office / retail / logistics / light_industrial / multifamily.", "logistics",
       aliases=("type", "use", "usage", "asset_type", "property_use")),
    _f("policy_type", "Policy type", "text", "Line of business; defaults to 'property' for a new location.", "property", aliases=("line_of_business", "lob")),
    _f("sector", "Sector", "text", "Sector / industry.", "Real estate", aliases=("industry", "sector_name", "gics_sector")),
    _f("nace_code", "NACE code", "text", "NACE code, if known — enables EU Taxonomy classification.", "68.20", aliases=("nace", "nace_rev2")),
    _f("construction_type", "Construction type", "vocab", "ISO construction class: frame / joisted_masonry / non_combustible / "
       "masonry_non_combustible / fire_resistive.", "masonry_non_combustible", vocab="construction_type",
       aliases=("construction", "construction_class", "iso_class", "iso_construction_class")),
    _f("epc_rating", "EPC rating", "vocab", "Energy Performance Certificate grade (A-G).", "B", vocab="epc_rating",
       aliases=("epc", "energy_label", "energy_rating", "epc_grade")),
    _f("minimum_safeguards_status", "Minimum-safeguards status", "vocab", "compliant / non_compliant, from your own OECD/UN/ILO "
       "counterparty screening.", "compliant", vocab="safeguards_status", aliases=("safeguards", "min_safeguards")),
    _f("counterparty_govt_level", "Counterparty government level", "vocab", "central / regional / local — leave blank for "
       "non-government counterparties (EU Taxonomy Art. 7(1) exclusion).", "central", vocab="govt_level", aliases=("govt_level", "government_level")),
    _f("irrigation_status", "Irrigation", "vocab", "irrigated / rain_fed / mixed.", "irrigated", vocab="irrigation", aliases=("irrigation", "irrigated")),
    _f("commodity", "Commodity", "vocab", "Must match a commodity on this platform (e.g. Cocoa, Coffee, Citrus).", "Cocoa",
       vocab="commodity", aliases=("crop", "product", "commodity_name")),
    _f("borrower_entity_id", "Counterparty ID (LEI)", "text", "LEI or other stable entity ID.", "5493001KJTIIGC8Y1R12", aliases=("lei", "entity_id", "counterparty_lei")),
    _f("no_stated_maturity", "No stated maturity", "vocab", "True for an exposure with no stated maturity by its nature "
       "(equity, perpetual) — EBA Q&A 2022_6515.", "true", vocab="boolean"),
    # values
    _f("appraised_value_eur", "Appraised value (EUR)", "money", "Current appraised / collateral value.", "12000000",
       aliases=("value", "appraised_value", "collateral_value", "market_value", "valuation")),
    _f("counterparty_evic_eur", "Counterparty EVIC (EUR)", "money", "Enterprise value including cash of the counterparty.", "185000000",
       aliases=("evic", "enterprise_value")),
    _f("outstanding_loan_balance_eur", "Outstanding balance (EUR)", "money", "Current outstanding principal — enables LTV.", "8400000",
       aliases=("outstanding", "balance", "outstanding_balance", "principal", "exposure", "ead")),
    _f("sum_insured_eur", "Sum insured (EUR)", "money", "Total insured value, if not broken into components.", "3700000",
       aliases=("tiv", "total_insured_value", "sum_insured", "insured_value")),
    _f("building_value_eur", "Building value (EUR)", "money", "TIV component: buildings.", "3000000", aliases=("building_value", "buildings")),
    _f("contents_value_eur", "Contents value (EUR)", "money", "TIV component: contents.", "500000", aliases=("contents_value", "contents", "bpp")),
    _f("business_interruption_value_eur", "Business interruption (EUR)", "money", "TIV component: business income.", "200000",
       aliases=("bi_value", "business_interruption", "bi", "business_income")),
    _f("motor_sum_insured_eur", "Motor sum insured (EUR)", "money", "Motor-vehicle sum insured at this location.", "150000", aliases=("motor", "motor_value")),
    _f("property_value_eur", "Property value (EUR)", "money", "Current market / appraised value.", "42000000",
       aliases=("value", "market_value", "property_value", "valuation", "gav")),
    _f("annual_noi_eur", "Annual NOI (EUR)", "money", "Annual net operating income.", "2400000", aliases=("noi", "net_operating_income")),
    _f("annual_gross_rental_revenue_eur", "Gross rental revenue (EUR)", "money", "Annual gross rental revenue before operating expenses.",
       "3600000", aliases=("gross_rent", "rental_revenue", "gross_rental_income")),
    _f("position_value_eur", "Position value (EUR)", "money", "Market value of the position.", "18500000",
       aliases=("value", "market_value", "position_value", "exposure", "mv")),
    _f("annual_spend_eur", "Annual spend (EUR)", "money", "Annual procurement spend from this plot.", "150000", aliases=("spend", "annual_spend", "purchases")),
    # other attributes
    _f("deductible_pct", "Deductible (fraction)", "fraction", "Policy deductible as a fraction (0.02 = 2%).", "0.02",
       aliases=("deductible",), range=(0, 1)),
    _f("year_built", "Year built", "int", "Year of construction.", "1998", aliases=("built", "year_of_construction", "yearbuilt", "construction_year"),
       range=(1800, 2100)),
    _f("number_of_stories", "Stories", "int", "Number of stories.", "3", aliases=("stories", "storeys", "floors", "number_of_floors"), range=(0, 200)),
    _f("cresta_zone", "CRESTA zone", "int", "EIOPA/CRESTA risk-zone number (Del. Reg. 2015/35 Annex IX).", "21", aliases=("cresta",), range=(1, 9999)),
    _f("loan_origination_date", "Origination date", "date", "YYYY-MM-DD.", "2022-03-01", aliases=("origination_date", "start_date", "drawdown_date")),
    _f("plot_geojson", "Plot boundary (GeoJSON)", "geojson", "EUDR plot boundary as a GeoJSON Polygon — required over 4 ha.",
       '{"type":"Polygon","coordinates":[[[-1.606,6.694],[-1.604,6.694],[-1.604,6.696],[-1.606,6.696],[-1.606,6.694]]]}',
       aliases=("geojson", "geometry", "boundary", "polygon")),
    _f("plot_area_ha", "Plot area (ha)", "fraction", "Hectares; computed from the boundary when given.", "2.3", aliases=("area_ha", "area", "hectares"),
       range=(0, 1_000_000)),
)}

# the validator's kind for each catalogue kind (upload_validation understands these)
VALIDATION_KIND = {"name": "text", "id": "text", "vocab": "vocab", "fraction": "number", "geojson": "text"}


def vocab_values(name: str) -> set[str]:
    return set(VOCABS[name].values)
