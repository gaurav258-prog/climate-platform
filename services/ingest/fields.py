"""The field catalogue: every field a customer file can carry, defined ONCE, for every sector.

A field says what it is (kind), what values it may take (vocabulary), what customers tend to call it (aliases), and
what counts as plausible (range). Sector templates (templates.py) are compositions of these fields. Everything that
reads a customer file works from this catalogue — validation, value matching, column profiling, the mapping editor,
the template workbook — so adding a sector means listing its fields, nothing else.

Vocabulary synonyms are EXACT equivalences only (ISO construction class numbers, spelling variants). A value that
is merely similar ("Concrete") is never mapped here; the customer maps it, and the mapping is recorded.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# PCAF Part A (3rd ed.): the asset classes, a building's energy sources and the energy bases of the mortgage method — one
# reference file (data/reference/pcaf/part_a_2025.json), read here so the file's lists are the vocabularies
_PCAF = json.loads((Path(__file__).resolve().parents[2] / "data" / "reference" / "pcaf" / "part_a_2025.json").read_text())
_MORTGAGES = _PCAF["mortgages"]


def norm_token(v) -> str:
    """Case, spacing and punctuation-insensitive form: 'Joisted Masonry' / 'joisted-masonry' → 'joisted_masonry';
    'Congo (DRC)' → 'congo_drc'; 'Österreich' stays 'österreich'."""
    return re.sub(r"[\W_]+", "_", str(v).strip().lower()).strip("_")   # any punctuation/space; letters of any script kept


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
    # FINREP counterparty sectors (Annex V, Part 1) and immovable-property collateral (Pillar 3 Template 5 rows 10-12)
    "counterparty_sector": Vocab(("central_bank", "general_government", "credit_institution", "other_financial_corporation",
                                  "non_financial_corporation", "household"),
                                 {"nfc": "non_financial_corporation", "corporate": "non_financial_corporation",
                                  "households": "household", "retail": "household", "ofc": "other_financial_corporation",
                                  "bank": "credit_institution", "government": "general_government"}),
    "immovable_collateral": Vocab(("residential", "commercial", "repossessed", "none"),
                                  {"rre": "residential", "cre": "commercial", "residential_immovable_property": "residential",
                                   "commercial_immovable_property": "commercial", "no": "none", "unsecured": "none"}),
    "irrigation": Vocab(("irrigated", "rain_fed", "mixed"), {"rainfed": "rain_fed"}),
    # the building-use classes of the damage curves (data/reference/occupancy.json, E169) — no synonyms: a warehouse or a
    # hotel is classed differently by different curve sets, so only the class names themselves are accepted
    "occupancy": Vocab(("residential", "commercial", "industrial", "transport", "infrastructure", "agriculture")),
    # own operational site types (services.intelligence.company_sites.SITE_TYPES)
    "site_type": Vocab(("hq", "factory", "warehouse", "distribution_centre", "office", "other"),
                       {"headquarters": "hq", "head_office": "hq", "plant": "factory", "mill": "factory",
                        "manufacturing_site": "factory", "dc": "distribution_centre", "distribution_center": "distribution_centre"}),
    "commodity": Vocab((), dynamic=True),            # the commodities on this platform (sc_commodities)
    "country": Vocab((), dynamic=True),
    "currency": Vocab((), dynamic=True),             # ISO 4217 codes any FX source or fixed rate covers, plus EUR              # ISO alpha-2 via every accepted written form (ref_country_names)
    "boolean": Vocab(("true", "false"), {"yes": "true", "y": "true", "1": "true", "no": "false", "n": "false", "0": "false"}),
    # Regulation (EU) 2023/1115: placing on the market, making available on the market, export (Art. 2(16), 2(18), 4, 5)
    "eudr_movement": Vocab(("placing", "making_available", "export"),
                           {"placing_on_the_market": "placing", "import": "placing", "making_available_on_the_market": "making_available"}),
    # Art. 2(15) operator, 2(15a) micro or small primary operator, 2(15b) downstream operator, 2(17) trader
    "eudr_role": Vocab(("operator", "micro_small_primary_operator", "downstream_operator", "trader")),
    "eudr_supplier_role": Vocab(("operator", "downstream_operator", "trader")),
    # an asset manager's funds (services/funds/registry.py: FUND_TYPES, SFDR_ARTICLES) and what a holding is
    "fund_type": Vocab(("fund", "sub_portfolio", "mandate", "fund_of_funds"),
                       {"sub_fund": "sub_portfolio", "subportfolio": "sub_portfolio", "segregated_mandate": "mandate",
                        "fof": "fund_of_funds", "funds_of_funds": "fund_of_funds"}),
    # Regulation (EU) 2019/2088 Art. 6, 8 and 9 — the manager's classification
    "sfdr_article": Vocab(("article_6", "article_8", "article_9"),
                          {"6": "article_6", "8": "article_8", "9": "article_9", "art_6": "article_6", "art_8": "article_8",
                           "art_9": "article_9", "article6": "article_6", "article8": "article_8", "article9": "article_9"}),
    "asset_class": Vocab(("equity", "corporate_bond", "sovereign_bond", "securitized", "etf", "fund", "other"),
                         {"share": "equity", "shares": "equity", "stock": "equity", "corporate_bonds": "corporate_bond",
                          "government_bond": "sovereign_bond", "govt_bond": "sovereign_bond", "abs": "securitized"}),
    # PCAF Part A, 3rd ed. (data/reference/pcaf/part_a_2025.json): the asset class a loan is in (chapter 5), the energy
    # sources a building uses (the scoped ones, plus biomass — refused with its reason) and the basis of its energy figure
    # (§5.5, Table 5.5-1). No synonyms: 'gas' or 'oil' could be more than one source.
    "pcaf_asset_class": Vocab(tuple(c["key"] for c in _PCAF["asset_classes"]), {"mortgage": "mortgages"}),
    "energy_source": Vocab((*_MORTGAGES["energy_sources"]["scope"], *_MORTGAGES["energy_sources"]["not_built"]),
                           {"district_heat": "district_heating", "fernwaerme": "district_heating"}),
    "energy_basis": Vocab(tuple(_MORTGAGES["energy_bases"])),
    "emission_factor_type": Vocab(tuple(_MORTGAGES["data_quality"]["factor_types"]["values"]),
                                  {"market_based": "supplier_specific", "location_based": "average"}),
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
    flow: bool = False               # money over a period (annual income, spend, revenue): converted at the period
                                     # AVERAGE rate; any other money field is a balance, converted at the CLOSING rate
    header_only: bool = False        # proposed for a column by its name only, never by its values alone: its values are
                                     # words another field also takes (E340)


def _f(name, label, kind, description, example, vocab=None, aliases=(), range=None, flow=False,  # noqa: A002
       header_only=False) -> FieldDef:
    return FieldDef(name, label, kind, description, example, vocab, tuple(aliases), range, flow, header_only)


_REF = "Your own {what} id. When you send the book again, rows with the same ID update that asset instead of adding a new one."

FIELDS: dict[str, FieldDef] = {f.name: f for f in (
    # identity & location — shared by every sector
    _f("external_ref", "Your asset ID", "id", _REF.format(what="asset"), "REF-000123",
       aliases=("id", "asset_id", "loan_id", "facility_id", "policy_id", "location_id", "property_id", "holding_id",
                "position_id", "plot_id", "farm_id", "reference", "ref", "your_asset_id", "account_number")),
    _f("latitude", "Latitude", "lat", "Decimal degrees.", "50.1109", aliases=("lat", "y", "latitude_dd", "gps_lat", "gps_n", "north", "n", "lat_dd", "breitengrad")),
    _f("longitude", "Longitude", "lon", "Decimal degrees.", "8.6821", aliases=("lon", "lng", "long", "x", "longitude_dd", "gps_lon", "gps_long", "gps_e", "east", "e", "lon_dd", "laengengrad")),
    _f("region", "Region", "text", "Free-text region / city.", "Frankfurt", aliases=("city", "state", "province", "area", "location")),
    _f("country", "Country", "vocab", "Country — ISO-2 code preferred (DE); a code (DEU, 276) or a name in any EU language "
       "(Deutschland, Germany) is matched.", "DE", vocab="country", aliases=("country_code", "iso2", "ctry", "cntry", "land", "pays")),
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
    _f("site_ref", "Site ID", "id", "Your own id for the site (as in your sites file), or the site id shown on the "
       "Operations page.", "SITE-0042", aliases=("site_id", "site_code", "site", "site_reference", "external_ref")),
    _f("site_name", "Site name", "name", "Free-text name of your own site (plant, warehouse, office).", "Valencia Mill",
       aliases=("name", "site", "facility", "facility_name", "plant", "location_name")),
    _f("address", "Address", "text", "Street address — used to locate the site when no coordinates are given.",
       "Carrer de Colon 1, 46004 Valencia, Spain", aliases=("street_address", "full_address", "location_address")),
    _f("site_type", "Site type", "vocab", "hq, factory, warehouse, distribution_centre, office or other.", "factory",
       vocab="site_type", aliases=("type", "facility_type", "category")),
    _f("held_from", "Held from", "date", "First day your undertaking held the site or sourced from the plot (YYYY-MM-DD). "
       "Leave out when it was before your records.", "2019-03-01",
       aliases=("acquired", "acquisition_date", "from", "start", "since", "contract_start")),
    _f("held_until", "Held until", "date", "First day it no longer held the site or sourced from the plot (YYYY-MM-DD). "
       "Leave out while it still does.", "2031-01-01",
       aliases=("disposed", "disposal_date", "until", "end", "closed", "contract_end")),
    _f("site_area_ha", "Site area (ha)", "fraction", "Area of the site in hectares (ESRS E4 counts the area of sites in or "
       "near biodiversity-sensitive areas).", "12.5", aliases=("area_ha", "area", "hectares", "site_area"), range=(0, 1_000_000)),
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
    _f("counterparty_sector", "Counterparty sector (FINREP)", "vocab", "central_bank / general_government / credit_institution / "
       "other_financial_corporation / non_financial_corporation / household (FINREP Annex V, Part 1).", "non_financial_corporation",
       vocab="counterparty_sector", aliases=("finrep_sector", "counterparty_type", "institutional_sector")),
    _f("immovable_collateral", "Immovable-property collateral", "vocab", "residential / commercial (by predominant use) / "
       "repossessed / none.", "residential", vocab="immovable_collateral", aliases=("re_collateral", "property_collateral")),
    _f("postal_address", "Postal address", "text", "The postal address of the plot or of the establishment it is farmed "
       "from. A micro or small primary operator may give it instead of the geolocation (EUDR Art. 4a(5)).",
       "Plot 7, Ejisu Road, Kumasi, Ghana", aliases=("postal", "plot_address", "establishment_address")),
    _f("irrigation_status", "Irrigation", "vocab", "irrigated / rain_fed / mixed.", "irrigated", vocab="irrigation", aliases=("irrigation", "irrigated")),
    _f("commodity", "Commodity", "vocab", "Must match a commodity on this platform (e.g. Cocoa, Coffee, Citrus).", "Cocoa",
       vocab="commodity", aliases=("crop", "product", "commodity_name")),
    _f("borrower_entity_id", "Counterparty ID (LEI)", "text", "LEI or other stable entity ID.", "5493001KJTIIGC8Y1R12", aliases=("lei", "entity_id", "counterparty_lei")),
    _f("no_stated_maturity", "No stated maturity", "vocab", "True for an exposure with no stated maturity by its nature "
       "(equity, perpetual) — EBA Q&A 2022_6515.", "true", vocab="boolean"),
    # values
    _f("appraised_value_eur", "Appraised value", "money", "Current appraised / collateral value.", "12000000",
       aliases=("value", "appraised_value", "collateral_value", "market_value", "valuation")),
    _f("counterparty_evic_eur", "Counterparty EVIC", "money", "Enterprise value including cash of the counterparty.", "185000000",
       aliases=("evic", "enterprise_value")),
    _f("outstanding_loan_balance_eur", "Outstanding balance", "money", "Current outstanding principal — enables LTV.", "8400000",
       aliases=("outstanding", "balance", "outstanding_balance", "principal", "exposure", "ead")),
    _f("sum_insured_eur", "Sum insured", "money", "Total insured value, if not broken into components.", "3700000",
       aliases=("tiv", "total_insured_value", "sum_insured", "insured_value")),
    _f("building_value_eur", "Building value", "money", "The building's own value, land excluded — what a damage curve's "
       "share is taken of. In an insurance schedule: the buildings component of the total insured value.", "3000000",
       aliases=("building_value", "buildings")),
    _f("occupancy", "Building use", "vocab", "What the building is used for — residential, commercial, industrial, "
       "transport, infrastructure or agriculture; it selects the building's damage curve. Left blank, the use is read "
       "from the asset type only where the type settles it.", "residential", vocab="occupancy",
       aliases=("building_use", "occupancy_class", "occupancy_type", "use_class")),
    _f("contents_value_eur", "Contents value", "money", "TIV component: contents.", "500000", aliases=("contents_value", "contents", "bpp")),
    _f("business_interruption_value_eur", "Business interruption", "money", "TIV component: business income.", "200000",
       aliases=("bi_value", "business_interruption", "bi", "business_income")),
    _f("motor_sum_insured_eur", "Motor sum insured", "money", "Motor-vehicle sum insured at this location.", "150000", aliases=("motor", "motor_value")),
    _f("property_value_eur", "Property value", "money", "Current market / appraised value.", "42000000",
       aliases=("value", "market_value", "property_value", "valuation", "gav")),
    _f("annual_noi_eur", "Annual NOI", "money", "Annual net operating income.", "2400000", aliases=("noi", "net_operating_income"), flow=True),
    _f("annual_gross_rental_revenue_eur", "Gross rental revenue", "money", "Annual gross rental revenue before operating expenses.",
       "3600000", aliases=("gross_rent", "rental_revenue", "gross_rental_income"), flow=True),
    _f("position_value_eur", "Position value", "money", "Market value of the position.", "18500000",
       aliases=("value", "market_value", "position_value", "exposure", "mv")),
    _f("annual_spend_eur", "Annual spend", "money", "Annual procurement spend from this plot.", "150000", aliases=("spend", "annual_spend", "purchases"), flow=True),
    _f("carrying_amount_eur", "Carrying amount", "money", "The site's carrying amount in the balance sheet at the period "
       "end (property, plant and equipment and other assets at the site) — converted at the closing rate of that day.",
       "11800000", aliases=("carrying_amount", "carrying_value", "book_value", "net_book_value", "nbv")),
    _f("carrying_amount_adapted_eur", "Carrying amount addressed by adaptation", "money", "The part of the site's "
       "carrying amount at the period end that adaptation actions address (ESRS E1: the share of assets at material "
       "physical risk addressed by adaptation actions) — at most the carrying amount.", "4000000",
       aliases=("adapted_amount", "carrying_amount_adapted", "addressed_by_adaptation")),
    _f("net_revenue_eur", "Net revenue", "money", "Net revenue from the business activities at the site over the year "
       "ending at the period end.", "36000000", aliases=("net_revenue", "revenue", "turnover", "sales"), flow=True),
    _f("annual_value_eur", "Site value", "money", "The site's asset value (the year-end carrying amount finance reports is "
       "sent separately, per reporting period).", "12000000", aliases=("value", "asset_value", "site_value")),
    _f("annual_throughput_eur", "Annual throughput", "money", "Annual value of the goods the site handles — the basis of "
       "business-interruption exposure.", "40000000", aliases=("throughput", "annual_throughput", "output_value"), flow=True),
    # other attributes
    _f("deductible_pct", "Deductible (fraction)", "fraction", "Policy deductible as a fraction (0.02 = 2%).", "0.02",
       aliases=("deductible",), range=(0, 1)),
    _f("year_built", "Year built", "int", "Year of construction.", "1998", aliases=("built", "year_of_construction", "yearbuilt", "construction_year"),
       range=(1800, 2100)),
    # EU Taxonomy activity 7.7 (buildings) — Del. Reg. 2021/2139 Annex I §7.7 and Appendix A (criteria/ccm_7_7.json)
    _f("ped_top15_evidence", "Top 15 % by primary energy demand", "vocab", "True where the building is evidenced to be "
       "within the top 15 % of the national or regional stock by operational primary energy demand (the alternative to "
       "EPC class A for a building built before 2021).", "false", vocab="boolean", aliases=("top15_ped", "ped_top_15")),
    _f("meets_new_building_criteria", "Meets §7.1 (built after 2020)", "vocab", "For a building built after 31 December "
       "2020: true where it meets the Taxonomy Section 7.1 construction criteria relevant at acquisition.", "true",
       vocab="boolean", aliases=("meets_7_1", "nzeb_minus_10")),
    _f("heating_rated_output_kw", "Heating / air-conditioning rated output (kW)", "int", "Effective rated output of the "
       "heating, ventilation or air-conditioning systems — over 290 kW makes a non-residential building 'large'.", "350",
       aliases=("hvac_kw", "rated_output_kw"), range=(0, 100000)),
    _f("energy_performance_monitoring", "Energy-performance monitoring", "vocab", "True where the building is operated "
       "through energy performance monitoring and assessment (required for a large non-residential building).", "true",
       vocab="boolean", aliases=("energy_monitoring", "bems")),
    _f("adaptation_plan_in_place", "Adaptation plan in place", "vocab", "True where adaptation solutions reducing the "
       "material physical climate risks are implemented under an adaptation plan (Appendix A, existing buildings).",
       "true", vocab="boolean", aliases=("adaptation_plan",)),
    _f("number_of_stories", "Stories", "int", "Number of stories.", "3", aliases=("stories", "storeys", "floors", "number_of_floors"), range=(0, 200)),
    _f("postal_code", "Postal code", "text", "The risk's postal code as written locally (10115, SW1A 1AA). Solvency II "
       "places each risk in its nat-cat risk zone by it (Del. Reg. 2015/35 Annex IX); without it the region's zones are "
       "grouped at their highest weight.", "10115", aliases=("postcode", "zip", "zip_code", "plz", "cap", "code_postal", "cp")),
    _f("loan_origination_date", "Origination date", "date", "YYYY-MM-DD.", "2022-03-01", aliases=("origination_date", "start_date", "drawdown_date")),
    # PCAF mortgages (§5.5): the attribution factor is the outstanding balance over the property's value at origination
    _f("pcaf_asset_class", "PCAF asset class", "vocab", "The loan's asset class in the PCAF financed-emissions standard — it "
       "sets how the loan's financed emissions are attributed. 'mortgages': a loan to buy or refinance a home lived in "
       "(not a home equity loan, not a loan to build or renovate).", "mortgages", vocab="pcaf_asset_class",
       aliases=("pcaf_class", "pcaf_asset_class", "financed_emissions_asset_class"),
       header_only=True),                    # 'commercial_real_estate' is also an asset type (E340)
    _f("property_value_at_origination_eur", "Property value at origination", "money", "The property's value when the loan "
       "was made: a mortgage's building emissions are attributed by the outstanding balance divided by this value (PCAF). "
       "A loan you refinance is a new loan, with the value of its own origination.", "400000",
       aliases=("origination_value", "value_at_origination", "original_value", "original_property_value",
                "initial_valuation", "property_value_origination")),
    _f("property_value_fixed_eur", "Property value fixed instead", "money", "Only where the value at origination cannot be "
       "obtained: the latest property value you have, kept fixed for the following years (PCAF) — once stated it stays, "
       "and a different value is refused. Needs your asset ID.", "420000",
       aliases=("fixed_property_value", "latest_property_value_fixed", "property_value_fixed")),
    _f("floor_area_m2", "Floor area (m²)", "fraction", "The financed home's floor area: an energy use per m² (from its energy "
       "label or from statistics) is multiplied by it. Give the same kind of floor area (net, usable, …) as that figure.",
       "95", aliases=("floor_area", "living_area", "area_m2", "floor_space", "wohnflaeche")),
    _f("plot_geojson", "Plot boundary (GeoJSON)", "geojson", "EUDR plot boundary as a GeoJSON Polygon — required over 4 ha.",
       '{"type":"Polygon","coordinates":[[[-1.606,6.694],[-1.604,6.694],[-1.604,6.696],[-1.606,6.696],[-1.606,6.694]]]}',
       aliases=("geojson", "geometry", "boundary", "polygon")),
    _f("currency", "Currency", "vocab", "ISO 4217 code of this row's amounts (e.g. USD). Overrides the currency declared for "
       "the file; leave out when every row is in that currency.", "USD", vocab="currency",
       aliases=("ccy", "currency_code", "cur", "curr", "iso_currency", "waehrung", "devise")),
    _f("book_date", "Book date", "date", "The date this row's figures describe (YYYY-MM-DD). Overrides the book date declared "
       "for the file. Balances convert at that day's rate; annual flows at the average of the 12 months to it.",
       "2026-06-30", aliases=("as_of", "as_of_date", "asof", "valuation_date", "reporting_date", "stichtag", "date")),
    _f("reporting_entity", "Reporting entity", "text", "Which of your legal entities holds this asset — its name or ID as set "
       "up under Admin → Entities. Leave out when the whole file belongs to one entity.", "Meridian Bank AG",
       aliases=("legal_entity", "booking_entity", "entity", "holding_entity", "subsidiary", "company_code")),
    _f("intragroup_counterparty", "Intragroup counterparty", "text", "Only when the other side is a company of your own group "
       "(an intragroup loan, a property let to a sister company): that entity's name or ID. Kept in its solo filing, "
       "removed from a consolidated filing that contains both.", "Meridian Leasing GmbH",
       aliases=("intragroup", "intercompany", "intercompany_counterparty", "group_counterparty", "ic_partner", "trading_partner")),
    _f("plot_area_ha", "Plot area (ha)", "fraction", "Hectares; computed from the boundary when given.", "2.3", aliases=("area_ha", "area", "hectares"),
       range=(0, 1_000_000)),
    # ── the banking book's counterparties (Pillar 3 Template 1 columns i-k: one counterparty, one figure) ──
    _f("counterparty_ref", "Counterparty ID", "id", "The counterparty's id exactly as your loan tape gives it in its "
       "'Counterparty ID (LEI)' column: its LEI, or your own stable id for it (at most 20 characters).", "5493001KJTIIGC8Y1R12",
       aliases=("borrower_entity_id", "counterparty_id", "counterparty_lei", "lei", "obligor_id", "customer_id")),
    _f("counterparty_name", "Counterparty name", "name", "The counterparty's name.", "Rheinstahl AG",
       aliases=("name", "borrower", "borrower_name", "obligor", "obligor_name", "company", "company_name")),
    _f("total_liabilities_eur", "Total liabilities and equity", "money", "The counterparty's total liabilities: its "
       "accounting liabilities and shareholders' equity, from its balance sheet (Pillar 3 Template 1 column i: your "
       "exposure compared to the counterparty's total liabilities).", "420000000",
       aliases=("total_liabilities", "total_liabilities_and_equity", "liabilities_and_equity")),
    _f("counterparty_revenue_eur", "Revenue", "money", "The counterparty's revenue for the financial year ending on the "
       "row's book date, from its accounts (Pillar 3 Template 1 column i: a sector-average scope 3 intensity per EUR "
       "million of revenue).", "310000000", aliases=("revenue", "revenue_eur", "annual_revenue", "turnover",
                                                     "net_turnover"), flow=True),
    # ── an asset manager's funds and their holdings by ISIN (services/ingest/fund_books.py) ──
    _f("fund_name", "Fund", "name", "The fund's name — on a holding, exactly as on its row of the Funds sheet.",
       "Kestrel Ridge European Equity", aliases=("fund", "portfolio", "portfolio_name", "product", "product_name")),
    _f("fund_type", "Fund type", "vocab", "fund, sub_portfolio, mandate or fund_of_funds.", "fund", vocab="fund_type",
       aliases=("type", "vehicle_type", "structure")),
    _f("sfdr_classification", "SFDR article", "vocab", "The article of Regulation (EU) 2019/2088 the fund discloses under "
       "— article_6, article_8 or article_9; your classification, never assumed.", "article_8", vocab="sfdr_article",
       aliases=("sfdr", "sfdr_article", "sfdr_category", "article")),
    _f("base_currency", "Base currency", "vocab", "The fund's base currency (ISO 4217).", "EUR", vocab="currency",
       aliases=("fund_currency", "reference_currency")),
    _f("parent_fund", "Parent fund", "text", "For a sub-portfolio: the fund it belongs to, by its name on this sheet.",
       "Kestrel Ridge Funds", aliases=("umbrella", "parent", "umbrella_fund")),
    _f("fund_lei", "Fund LEI", "id", "The fund's LEI, if it has one — checked against the GLEIF register.",
       "5493001KJTIIGC8Y1R12", aliases=("lei", "fund_legal_entity_identifier")),
    _f("isin", "ISIN", "id", "The security's ISIN (12 characters, ISO 6166).", "DE0007164600",
       aliases=("isin_code", "security_isin", "instrument_isin", "identifier")),
    _f("market_value_eur", "Market value", "money", "The position's market value on its as-of date.", "18500000",
       aliases=("market_value", "mv", "value", "position_value", "valuation")),
    _f("asset_class", "Asset class", "vocab", "equity, corporate_bond, sovereign_bond, securitized, etf, fund or other.",
       "equity", vocab="asset_class", aliases=("instrument_type", "security_type", "class")),
    # ── the figures an asset manager holds about a company it holds, for one financial year (services/ingest/fund_books.py
    #    ISSUER_FIGURES; the same figures a holding may carry by the API, services/funds/holding.IssuerFigures) ──
    _f("revenue_eur", "Revenue", "money", "The company's revenue for the financial year ending on the row's date — a "
       "yearly figure, converted at the average rate of that year.", "31200000000",
       aliases=("revenue", "turnover", "net_turnover", "sales"), flow=True),
    _f("evic_eur", "EVIC", "money", "The company's enterprise value including cash at the financial year end (market "
       "capitalisation, total debt and cash) — what financed emissions are attributed by.", "210000000000",
       aliases=("evic", "enterprise_value", "enterprise_value_including_cash")),
    _f("physical_asset_value_eur", "Physical asset value", "money", "The company's buildings, plant, machinery and contents "
       "at the financial year end — land excluded: what a site's yearly loss is a share of.", "5400000000",
       aliases=("physical_assets", "ppe", "property_plant_equipment", "tangible_assets")),
    _f("scope1_tco2e", "Scope 1 emissions", "fraction", "The company's direct greenhouse-gas emissions for the year, in "
       "tonnes of CO2 equivalent.", "30000", aliases=("scope_1", "scope1", "ghg_scope1"), range=(0, 1e12)),
    _f("scope2_tco2e", "Scope 2 emissions", "fraction", "Emissions from the energy the company bought for the year, in "
       "tonnes of CO2 equivalent.", "45000", aliases=("scope_2", "scope2", "ghg_scope2"), range=(0, 1e12)),
    _f("scope3_tco2e", "Scope 3 emissions", "fraction", "The company's other indirect emissions for the year, in tonnes of "
       "CO2 equivalent.", "4300000", aliases=("scope_3", "scope3", "ghg_scope3"), range=(0, 1e13)),
    _f("energy_consumption_gwh", "Energy consumption", "fraction", "The company's energy consumption for the year, in GWh.",
       "410", aliases=("energy_gwh", "energy_consumption"), range=(0, 1e9)),
    _f("non_renewable_consumption_pct", "Non-renewable energy consumed", "fraction", "The share of the company's energy "
       "consumption from non-renewable sources, in per cent.", "62", aliases=("non_renewable_consumption",), range=(0, 100)),
    _f("non_renewable_production_pct", "Non-renewable energy produced", "fraction", "For an energy producer: the share of "
       "its energy production from non-renewable sources, in per cent.", "40", aliases=("non_renewable_production",),
       range=(0, 100)),
    _f("biodiversity_sensitive_ops", "Sites near sensitive areas", "vocab", "Whether the company has sites or operations in "
       "or near biodiversity-sensitive areas whose activities negatively affect them: yes or no.", "no", vocab="boolean",
       aliases=("biodiversity_sensitive", "near_sensitive_areas")),
    _f("emissions_to_water_tonnes", "Emissions to water", "fraction", "Tonnes of emissions to water the company generated "
       "in the year.", "12", aliases=("water_emissions",), range=(0, 1e12)),
    _f("hazardous_waste_tonnes", "Hazardous waste", "fraction", "Tonnes of hazardous and radioactive waste the company "
       "generated in the year.", "850", aliases=("hazardous_waste",), range=(0, 1e12)),
    _f("ungc_oecd_violation", "UN Global Compact / OECD violation", "vocab", "Whether the company has been involved in "
       "violations of the UN Global Compact principles or the OECD Guidelines: yes or no.", "no", vocab="boolean",
       aliases=("ungc_violation",)),
    _f("ungc_oecd_no_monitoring", "No compliance processes", "vocab", "Whether the company lacks processes to monitor "
       "compliance with the UN Global Compact principles or the OECD Guidelines: yes or no.", "no", vocab="boolean",
       aliases=("ungc_no_monitoring",)),
    _f("gender_pay_gap_pct", "Gender pay gap", "fraction", "The company's unadjusted gender pay gap, in per cent.", "11.5",
       aliases=("pay_gap",), range=(-100, 100)),
    _f("board_female_pct", "Women on the board", "fraction", "Female board members as a share of all board members, in "
       "per cent.", "38", aliases=("board_gender_diversity",), range=(0, 100)),
    _f("controversial_weapons", "Controversial weapons", "vocab", "Whether the company is involved in the manufacture or "
       "selling of controversial weapons: yes or no.", "no", vocab="boolean", aliases=("weapons",)),
    _f("taxonomy_eligible_pct", "Taxonomy-eligible turnover", "fraction", "The share of the company's turnover from "
       "Taxonomy-eligible activities, as the company reports it, in per cent.", "41", range=(0, 100)),
    _f("taxonomy_aligned_pct", "Taxonomy-aligned turnover", "fraction", "The share of the company's turnover from "
       "Taxonomy-aligned activities, as the company reports it, in per cent.", "12.5", range=(0, 100)),
    _f("taxonomy_aligned_capex_pct", "Taxonomy-aligned CapEx", "fraction", "The share of the company's capital expenditure "
       "that is Taxonomy-aligned, as the company reports it, in per cent.", "18", range=(0, 100)),
    _f("taxonomy_fossil_gas_aligned_pct", "Aligned turnover from fossil gas", "fraction", "The part of the aligned turnover "
       "from fossil-gas activities, in per cent of turnover.", "0", range=(0, 100)),
    _f("taxonomy_nuclear_aligned_pct", "Aligned turnover from nuclear", "fraction", "The part of the aligned turnover from "
       "nuclear activities, in per cent of turnover.", "0", range=(0, 100)),
    _f("taxonomy_fossil_gas_aligned_capex_pct", "Aligned CapEx from fossil gas", "fraction", "The part of the aligned "
       "capital expenditure from fossil-gas activities, in per cent of CapEx.", "0", range=(0, 100)),
    _f("taxonomy_nuclear_aligned_capex_pct", "Aligned CapEx from nuclear", "fraction", "The part of the aligned capital "
       "expenditure from nuclear activities, in per cent of CapEx.", "0", range=(0, 100)),
    _f("taxonomy_dnsh_ok", "Does no significant harm", "vocab", "Whether the company's aligned activities meet the "
       "do-no-significant-harm criteria: yes or no; leave blank where it is not assessed separately.", "yes",
       vocab="boolean", aliases=("dnsh",)),
    _f("taxonomy_min_safeguards_ok", "Meets minimum safeguards", "vocab", "Whether the company meets the Taxonomy's "
       "minimum safeguards: yes or no; leave blank where it is not assessed separately.", "yes", vocab="boolean",
       aliases=("minimum_safeguards", "min_safeguards")),
    # ── EUDR (Regulation (EU) 2023/1115): parties, placings / exports and the plots they came from ──
    _f("party_name", "Name", "name", "The business or person's name (Art. 9(1)(e)-(f)).", "Ashanti Cocoa Cooperative",
       aliases=("name", "supplier", "supplier_name", "customer", "customer_name", "company", "company_name")),
    _f("trade_name", "Trade name", "text", "Registered trade name or trade mark (Art. 5(3)), or the product's trade name "
       "(Annex II point 2).", "Golden Bean", aliases=("trade_mark", "brand", "registered_trade_name")),
    _f("contact_email", "Email", "text", "Email address (Art. 9(1)(e)-(f)).", "trade@example.com", aliases=("email", "e_mail", "mail")),
    _f("web_address", "Web address", "text", "Web address, if available (Art. 5(3)).", "https://example.com",
       aliases=("website", "url", "web", "homepage")),
    _f("party_ref", "Your party ID", "id", _REF.format(what="supplier / customer"), "SUP-0042",
       aliases=("external_ref", "supplier_id", "customer_id", "party_id", "vendor_id", "id")),
    _f("supplier_ref", "Supplier ID", "id", "Your own id of the supplier (as in your suppliers file).", "SUP-0042",
       aliases=("supplier", "supplier_id", "vendor", "vendor_id")),
    _f("customer_ref", "Customer ID", "id", "Your own id of the customer (as in your customers file).", "CUS-0007",
       aliases=("customer", "customer_id", "buyer", "buyer_id")),
    _f("movement_ref", "Shipment ID", "id", "Your own id of this placing on the market, making available or export "
       "(e.g. the consignment or contract line).", "SHP-2027-0001", aliases=("shipment", "shipment_id", "consignment",
                                                                              "consignment_id", "lot", "lot_id", "external_ref")),
    _f("movement_kind", "Placing, making available or export", "vocab", "placing, making_available or export.", "placing",
       vocab="eudr_movement", aliases=("kind", "movement", "activity", "flow")),
    _f("actor_role", "Your role", "vocab", "Your role in it: operator, micro_small_primary_operator, downstream_operator "
       "or trader (Art. 2(15)-(17)).", "operator", vocab="eudr_role", aliases=("role", "eudr_role")),
    _f("supplier_role", "Supplier's role", "vocab", "What your supplier is for these products: operator, downstream_operator "
       "or trader — where it is an operator, give the reference numbers of its statements or its declaration identifiers "
       "(Art. 5(3)(a)).", "operator", vocab="eudr_supplier_role", aliases=("supplier_type", "supplier_is")),
    _f("planned_on", "Date", "date", "The date of the placing on the market, making available or export (YYYY-MM-DD).",
       "2027-01-15", aliases=("date", "placing_date", "export_date", "shipment_date")),
    _f("hs_code", "HS code", "id", "Harmonised System code, 4 to 10 digits, no spaces (Annex II point 2).", "180100",
       aliases=("hs", "cn_code", "tariff_code", "commodity_code", "taric")),
    _f("description", "Description", "text", "Free-text description of the product (Annex II point 2).", "Cocoa beans, whole, raw",
       aliases=("product", "product_description", "goods_description")),
    _f("scientific_names", "Scientific names", "text", "For wood: the full scientific names of the species, separated by ';' "
       "(Annex II point 2).", "Tectona grandis", aliases=("species", "scientific_name", "botanical_name")),
    _f("customs_flow", "Through customs", "vocab", "true when the goods enter or leave the market through customs: the "
       "quantity is then in kilograms of net mass (Annex II point 2).", "true", vocab="boolean",
       aliases=("customs", "import_export", "via_customs")),
    _f("net_mass_kg", "Net mass (kg)", "fraction", "Kilograms of net mass.", "25000", aliases=("net_mass", "net_weight_kg", "kg"),
       range=(0, 1e12)),
    _f("mass_deviation_pct", "Net mass estimate / deviation (%)", "fraction", "Outside customs: the percentage estimate or "
       "deviation of the net mass (Annex II point 2).", "5", aliases=("deviation_pct", "mass_deviation"), range=(0, 100)),
    _f("supplementary_unit", "Supplementary unit", "text", "The supplementary unit of Annex I to Regulation (EEC) No 2658/87 "
       "for the HS code, where applicable.", "p/st", aliases=("supp_unit",)),
    _f("supplementary_qty", "Supplementary quantity", "fraction", "The quantity in that unit.", "120",
       aliases=("supp_qty", "supplementary_quantity"), range=(0, 1e12)),
    _f("volume_m3", "Volume (m³)", "fraction", "Where applicable, volume instead of net mass (outside customs).", "40",
       aliases=("volume", "m3"), range=(0, 1e12)),
    _f("items_count", "Number of items", "int", "Where applicable, number of items (outside customs).", "120",
       aliases=("items", "units", "pieces")),
    _f("upstream_refs", "Reference numbers received", "text", "When your supplier is an operator: the reference numbers of its "
       "due diligence statements or its declaration identifier, separated by ';' (Art. 5(3)(a)).", "25NLXYZ0000001",
       aliases=("dds_reference", "reference_numbers", "declaration_identifier")),
    _f("plot_ref", "Plot ID", "id", "Your own id of the plot (as in your plots file).", "PLOT-0012",
       aliases=("plot", "plot_id", "farm_id", "field_id")),
    _f("production_from", "Produced from", "date", "First day of production on the plot for this shipment (Art. 9(1)(d)).",
       "2025-10-01", aliases=("harvest_from", "production_start", "from")),
    _f("production_to", "Produced until", "date", "Last day of production on the plot for this shipment (Art. 9(1)(d)).",
       "2026-03-31", aliases=("harvest_to", "production_end", "to")),
    # a mortgaged building's energy use, one row per energy source (PCAF §5.5: Σ energy × emission factor per source)
    _f("loan_ref", "Your asset ID of the loan", "id", "The loan's own id, as on your loan tape (Your asset ID).", "WH-00001",
       aliases=("loan_id", "external_ref", "asset_id", "facility_id", "your_asset_id", "loan_reference")),
    _f("energy_source", "Energy source", "vocab", "One row per source the building uses: electricity, natural_gas, "
       "heating_oil, lpg, coal, district_heating or district_cooling.", "natural_gas", vocab="energy_source",
       aliases=("fuel", "energy_carrier", "carrier", "fuel_type", "energietraeger")),
    _f("energy_basis", "Energy figure from", "vocab", "Where the energy figure comes from — it sets the PCAF data quality "
       "score: metered (the year's actual consumption), energy_label (kWh per m² from the official energy label), "
       "statistics_per_m2 (kWh per m² from statistics for the building's type and place) or statistics_per_building "
       "(kWh per building from such statistics).", "energy_label", vocab="energy_basis",
       aliases=("energy_data_basis", "basis", "energy_figure_basis")),
    _f("annual_kwh", "Energy per year (kWh)", "fraction", "Metered: the building's consumption of this source over a year. "
       "Statistics per building: the energy of this source per building per year.", "4200",
       aliases=("kwh", "kwh_per_year", "annual_consumption_kwh", "consumption_kwh")),
    _f("kwh_per_m2", "Energy per m² per year (kWh)", "fraction", "Energy label or statistics per m²: the energy of this "
       "source per m² of floor area per year — multiplied by the loan's floor area.", "120",
       aliases=("kwh_m2", "energy_kwh_m2", "kwh_per_sqm", "specific_energy_kwh_m2")),
    _f("buildings", "Number of buildings", "int", "Statistics per building: how many buildings the loan finances.", "1",
       aliases=("number_of_buildings", "n_buildings", "building_count")),
    _f("emission_factor_kg_per_kwh", "Emission factor (kg CO₂e per kWh)", "fraction", "The energy source's greenhouse-gas "
       "emission factor, in kilograms of CO₂ equivalent per kWh.", "0.201",
       aliases=("emission_factor", "ef", "kgco2e_per_kwh", "kg_co2e_kwh")),
    _f("emission_factor_type", "Emission factor type", "vocab", "supplier_specific (the energy supplier's own factor; for "
       "electricity the market-based one) or average (the average for the area; for electricity the location-based one).",
       "average", vocab="emission_factor_type", aliases=("factor_type", "ef_type")),
    _f("emission_factor_source", "Emission factor source", "text", "Where the factor comes from: its publication and year.",
       "GEG 2024, Anlage 9", aliases=("ef_source", "factor_source")),
    _f("energy_year", "Year of the energy figure", "int", "The year the energy figure describes.", "2025",
       aliases=("data_year", "consumption_year"), range=(1990, 2100)),
)}

# the validator's kind for each catalogue kind (upload_validation understands these)
VALIDATION_KIND = {"name": "text", "id": "text", "vocab": "vocab", "fraction": "number", "geojson": "text"}


def vocab_values(name: str) -> set[str]:
    return set(VOCABS[name].values)
