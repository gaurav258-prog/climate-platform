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
}


def template_fields(key: str) -> list[dict]:
    """The field list a mapping editor shows (for plots, as if a boundary column may be present)."""
    from services.ingest.upload_validation import enrich_specs
    tpl = TEMPLATES[key]
    return enrich_specs(tpl.specs(pd.DataFrame(columns=["plot_geojson"] if key == "supply_plots" else [])))


def templates_for(org_type: str) -> list[Template]:
    return [t for t in TEMPLATES.values() if t.org_type == org_type]
