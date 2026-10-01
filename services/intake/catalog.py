"""The templates a customer can send, one per sector book: accepted formats, field specs, the value that ties the
file together, and the sector rules (services.ingest.sector_ingest) that turn a row into an asset.

Every intake step — security, mapping, value matching, profiling, checks, matching, landing, the API push — is
generic over this registry. Adding a sector = its fields in services/ingest/templates.py, its Sector rules in
services/ingest/sector_ingest.py, and one line here."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import pandas as pd

from services.ingest import sector_ingest as si
from services.ingest import templates as T
from services.ingest.sector_contract import Sector


@dataclass(frozen=True)
class Template:
    key: str
    sector: Sector
    org_type: str                # the organisation type whose book this is (a token/user of another type is refused)
    label: str
    formats: tuple[str, ...]
    specs: Callable[[pd.DataFrame], list[dict]]
    value_field: Callable[[pd.DataFrame], Optional[str]]
    audit_action: str
    precheck: Optional[Callable[[pd.DataFrame], Optional[dict]]] = None   # returns an error dict, or None


def _insurance_valuation(df: pd.DataFrame) -> Optional[dict]:
    comps = {"building_value_eur", "contents_value_eur", "business_interruption_value_eur"}
    if "sum_insured_eur" not in df.columns and not (comps & set(df.columns)):
        return {"error": "missing_valuation", "message": "Provide either sum_insured_eur, or at least one of "
                "building_value_eur / contents_value_eur / business_interruption_value_eur."}
    return None


def _plot_specs(df: pd.DataFrame) -> list[dict]:
    specs = [dict(f) for f in T.PLOT_TEMPLATE_FIELDS]
    if "plot_geojson" in df.columns:   # a boundary-only row derives its point from the polygon
        for f in specs:
            if f["name"] in ("latitude", "longitude"):
                f["required"] = False
    return specs


def _site_specs(df: pd.DataFrame) -> list[dict]:
    specs = [dict(f) for f in T.SITE_TEMPLATE_FIELDS]
    if "address" in df.columns:        # an address-only row is located from its address (a row neither has is rejected)
        for f in specs:
            if f["name"] in ("latitude", "longitude"):
                f["required"] = False
    return specs


TEMPLATES: dict[str, Template] = {
    "bank_assets": Template("bank_assets", si.BANK, "bank", "loan tape", ("csv", "xlsx"), lambda df: T.ASSET_TEMPLATE_FIELDS,
                            lambda df: "appraised_value_eur", "assets.upload"),
    "insurance_policies": Template("insurance_policies", si.INSURANCE, "insurer", "Statement of Values", ("csv", "xlsx"),
                                   lambda df: T.POLICY_TEMPLATE_FIELDS,
                                   lambda df: "sum_insured_eur" if "sum_insured_eur" in df.columns else "building_value_eur",
                                   "policies.upload", _insurance_valuation),
    "realestate_properties": Template("realestate_properties", si.REALESTATE, "reit", "property schedule", ("csv", "xlsx"),
                                      lambda df: T.PROPERTY_TEMPLATE_FIELDS, lambda df: "property_value_eur",
                                      "properties.upload"),
    "assetmgmt_holdings": Template("assetmgmt_holdings", si.HOLDINGS, "asset_manager", "holdings book", ("csv", "xlsx"),
                                   lambda df: T.HOLDING_TEMPLATE_FIELDS, lambda df: "position_value_eur", "holdings.upload"),
    "supply_plots": Template("supply_plots", si.PLOTS, "manufacturer", "sourcing plots", ("csv",), _plot_specs,
                             lambda df: "annual_spend_eur", "plots.upload"),
    "company_sites": Template("company_sites", si.SITES, "manufacturer", "own sites", ("csv", "xlsx"), _site_specs,
                              lambda df: "annual_value_eur" if "annual_value_eur" in df.columns else None, "sites.upload"),
    "site_year_end_values": Template("site_year_end_values", si.YEAR_END, "manufacturer", "sites' year-end values",
                                     ("csv", "xlsx"), lambda df: T.SITE_YEAR_END_TEMPLATE_FIELDS,
                                     lambda df: "carrying_amount_eur" if "carrying_amount_eur" in df.columns else "net_revenue_eur",
                                     "sites.year_end.upload"),
    # EUDR (Regulation (EU) 2023/1115): the parties, each placing / making available / export, and the plots it came from
    "eudr_suppliers": Template("eudr_suppliers", si.SECTORS["eudr_suppliers"], "manufacturer", "suppliers", ("csv", "xlsx"),
                               lambda df: T.EUDR_SUPPLIER_TEMPLATE_FIELDS, lambda df: None, "eudr.suppliers.upload"),
    "eudr_customers": Template("eudr_customers", si.SECTORS["eudr_customers"], "manufacturer", "customers", ("csv", "xlsx"),
                               lambda df: T.EUDR_CUSTOMER_TEMPLATE_FIELDS, lambda df: None, "eudr.customers.upload"),
    "eudr_movements": Template("eudr_movements", si.SECTORS["eudr_movements"], "manufacturer",
                               "placings on the market and exports", ("csv", "xlsx"), lambda df: T.EUDR_MOVEMENT_TEMPLATE_FIELDS,
                               lambda df: "net_mass_kg" if "net_mass_kg" in df.columns else None, "eudr.movements.upload"),
    "eudr_movement_plots": Template("eudr_movement_plots", si.SECTORS["eudr_movement_plots"], "manufacturer",
                                    "the plots each shipment came from", ("csv", "xlsx"),
                                    lambda df: T.EUDR_MOVEMENT_PLOT_TEMPLATE_FIELDS, lambda df: None, "eudr.movement_plots.upload"),
}


def template_fields(key: str) -> list[dict]:
    """The field list a mapping editor shows (for plots, as if a boundary column may be present)."""
    from services.ingest.upload_validation import enrich_specs
    tpl = TEMPLATES[key]
    optional_location = {"supply_plots": ["plot_geojson"], "company_sites": ["address"]}.get(key, [])
    return enrich_specs(tpl.specs(pd.DataFrame(columns=optional_location)))


def templates_for(org_type: str) -> list[Template]:
    return [t for t in TEMPLATES.values() if t.org_type == org_type]
