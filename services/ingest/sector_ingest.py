"""Land validated customer rows into each sector's book — the one implementation both the live upload and a
4-eyes-approved batch (replayed from the stored file) call.

Every function takes ONLY rows that already passed the intake controls (validated and normalised) and returns
{"n_landed", "value_landed", "cell_coords", "notes"}. A row a sector rule cannot land (no valuation, unknown
commodity, bad geometry) is reported in notes and in the landing check — never silently. Scoring of new
locations is dispatched by the pipeline after landing, never here.
"""
from __future__ import annotations

import uuid

import h3
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.ingest.templates import (
    CONSTRUCTION_TYPES,
    EPC_RATINGS,
    IRRIGATION_VALUES,
    SAFEGUARDS_STATUSES,
)


def _norm_irrigation(value):
    v = (str(value).strip().lower() if value is not None and not (isinstance(value, float) and pd.isna(value)) else "") or None
    return v if v in IRRIGATION_VALUES else None   # unrecognised → treated as undeclared, never guessed


def ingest_bank(session: Session, org_id: str, df: pd.DataFrame) -> dict:
    from services.ingest.portfolio_ingest import ingest_bank_assets
    res = ingest_bank_assets(session, org_id, df.to_dict("records"), dispatch_scoring=False)
    return {"n_landed": res["n_ingested"], "value_landed": res.get("value_ingested", 0.0),
            "cell_coords": res.get("cell_coords", {}), "notes": {"skipped": res["skipped"]}}


def ingest_insurance(session: Session, org_id: str, df: pd.DataFrame) -> dict:
    from services.governance.entities import default_reporting_entity
    default_entity = default_reporting_entity(session, org_id)
    records, cell_coords = [], {}
    for _, row in df.iterrows():
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
        except (TypeError, ValueError):
            continue
        building = float(row["building_value_eur"]) if "building_value_eur" in df.columns and pd.notna(row.get("building_value_eur")) else None
        contents = float(row["contents_value_eur"]) if "contents_value_eur" in df.columns and pd.notna(row.get("contents_value_eur")) else None
        bi = float(row["business_interruption_value_eur"]) if "business_interruption_value_eur" in df.columns and pd.notna(row.get("business_interruption_value_eur")) else None
        if building is not None or contents is not None or bi is not None:
            sum_insured = (building or 0) + (contents or 0) + (bi or 0)
        elif "sum_insured_eur" in df.columns and pd.notna(row.get("sum_insured_eur")):
            sum_insured = float(row["sum_insured_eur"])
        else:
            continue  # no valuation data for this row -- skip, don't fabricate a TIV
        construction = str(row["construction_type"]).strip().lower() if "construction_type" in df.columns and pd.notna(row.get("construction_type")) else None
        if construction and construction not in CONSTRUCTION_TYPES:
            construction = None  # unrecognized value -- omit rather than violate the DB CHECK constraint
        cell = h3.latlng_to_cell(lat, lon, 8)
        cell_coords[cell] = (lat, lon)
        records.append({
            "policy_id": str(uuid.uuid4()), "org_id": org_id, "reporting_entity_id": default_entity,
            "policy_name": str(row["policy_name"]),
            "policy_type": str(row["policy_type"]) if "policy_type" in df.columns and pd.notna(row.get("policy_type")) else "property",
            "latitude": lat, "longitude": lon, "h3_cell": cell,
            "region": str(row["region"]) if "region" in df.columns and pd.notna(row.get("region")) else None,
            "country": str(row["country"]) if "country" in df.columns and pd.notna(row.get("country")) else None,
            "sum_insured_eur": sum_insured,
            "building_value_eur": building, "contents_value_eur": contents, "business_interruption_value_eur": bi,
            "construction_type": construction,
            "year_built": int(row["year_built"]) if "year_built" in df.columns and pd.notna(row.get("year_built")) else None,
            "number_of_stories": int(row["number_of_stories"]) if "number_of_stories" in df.columns and pd.notna(row.get("number_of_stories")) else None,
            "deductible_pct": float(row["deductible_pct"]) if "deductible_pct" in df.columns and pd.notna(row.get("deductible_pct")) else 0.02,
            "cresta_zone": int(row["cresta_zone"]) if "cresta_zone" in df.columns and pd.notna(row.get("cresta_zone")) else None,
            "motor_sum_insured_eur": float(row["motor_sum_insured_eur"]) if "motor_sum_insured_eur" in df.columns and pd.notna(row.get("motor_sum_insured_eur")) else None,
        })
    if not records:
        return {"n_landed": 0, "value_landed": 0.0, "cell_coords": {}, "notes": {}}

    session.execute(text("""
        INSERT INTO portfolio_entities (entity_id, org_id, vertical, entity_name, entity_type, latitude, longitude,
                                         h3_cell, region, country, primary_value_eur,
                                         construction_type, year_built, number_of_stories, reporting_entity_id)
        VALUES (:policy_id, :org_id, 'insurance', :policy_name, :policy_type, :latitude, :longitude,
                :h3_cell, :region, :country, :sum_insured_eur,
                :construction_type, :year_built, :number_of_stories, CAST(:reporting_entity_id AS uuid))
    """), records)
    session.execute(text("""
        INSERT INTO ext_insurance (entity_id, deductible_pct, building_value_eur, contents_value_eur,
                                    business_interruption_value_eur, cresta_zone, motor_sum_insured_eur)
        VALUES (:policy_id, :deductible_pct, :building_value_eur, :contents_value_eur,
                :business_interruption_value_eur, :cresta_zone, :motor_sum_insured_eur)
    """), records)
    return {"n_landed": len(records), "value_landed": float(sum(r["sum_insured_eur"] for r in records)),
            "cell_coords": cell_coords, "notes": {}}


def ingest_realestate(session: Session, org_id: str, df: pd.DataFrame) -> dict:
    from services.governance.entities import default_reporting_entity
    default_entity = default_reporting_entity(session, org_id)
    records, cell_coords = [], {}
    for _, row in df.iterrows():
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
            value_eur = float(row["property_value_eur"])
            noi_eur = float(row["annual_noi_eur"])
        except (TypeError, ValueError):
            continue  # a row with an unparsable required field is skipped, not fatal to the whole upload
        construction = str(row["construction_type"]).strip().lower() if "construction_type" in df.columns and pd.notna(row.get("construction_type")) else None
        if construction and construction not in CONSTRUCTION_TYPES:
            construction = None
        epc = str(row["epc_rating"]).strip().upper() if "epc_rating" in df.columns and pd.notna(row.get("epc_rating")) else None
        if epc and epc not in EPC_RATINGS:
            epc = None
        safeguards = str(row["minimum_safeguards_status"]).strip().lower() if "minimum_safeguards_status" in df.columns and pd.notna(row.get("minimum_safeguards_status")) else None
        if safeguards and safeguards not in SAFEGUARDS_STATUSES:
            safeguards = None
        gross_revenue = None
        if "annual_gross_rental_revenue_eur" in df.columns and pd.notna(row.get("annual_gross_rental_revenue_eur")):
            try:
                gross_revenue = float(row["annual_gross_rental_revenue_eur"])
            except (TypeError, ValueError):
                gross_revenue = None
        cell = h3.latlng_to_cell(lat, lon, 8)
        cell_coords[cell] = (lat, lon)
        records.append({
            "entity_id": str(uuid.uuid4()), "org_id": org_id, "reporting_entity_id": default_entity,
            "entity_name": str(row["property_name"]), "entity_type": str(row["property_type"]),
            "latitude": lat, "longitude": lon, "h3_cell": cell,
            "region": str(row["region"]) if "region" in df.columns and pd.notna(row.get("region")) else None,
            "country": str(row["country"]) if "country" in df.columns and pd.notna(row.get("country")) else None,
            "primary_value_eur": value_eur, "annual_noi_eur": noi_eur,
            "annual_gross_rental_revenue_eur": gross_revenue,
            "construction_type": construction,
            "year_built": int(row["year_built"]) if "year_built" in df.columns and pd.notna(row.get("year_built")) else None,
            "number_of_stories": int(row["number_of_stories"]) if "number_of_stories" in df.columns and pd.notna(row.get("number_of_stories")) else None,
            "epc_rating": epc,
            "borrower_entity_id": str(row["borrower_entity_id"]) if "borrower_entity_id" in df.columns and pd.notna(row.get("borrower_entity_id")) else None,
            "minimum_safeguards_status": safeguards,
        })
    if not records:
        return {"n_landed": 0, "value_landed": 0.0, "cell_coords": {}, "notes": {}}

    session.execute(text("""
        INSERT INTO portfolio_entities (entity_id, org_id, vertical, entity_name, entity_type,
                                         latitude, longitude, h3_cell, region, country,
                                         primary_value_eur, construction_type, year_built, number_of_stories,
                                         borrower_entity_id, minimum_safeguards_status, reporting_entity_id)
        VALUES (:entity_id, :org_id, 'realestate', :entity_name, :entity_type,
                :latitude, :longitude, :h3_cell, :region, :country,
                :primary_value_eur, :construction_type, :year_built, :number_of_stories,
                :borrower_entity_id, :minimum_safeguards_status, CAST(:reporting_entity_id AS uuid))
    """), records)
    session.execute(text("""
        INSERT INTO ext_realestate (entity_id, annual_noi_eur, epc_rating, annual_gross_rental_revenue_eur)
        VALUES (:entity_id, :annual_noi_eur, :epc_rating, :annual_gross_rental_revenue_eur)
    """), records)
    return {"n_landed": len(records), "value_landed": float(sum(r["primary_value_eur"] for r in records)),
            "cell_coords": cell_coords, "notes": {}}


def ingest_holdings(session: Session, org_id: str, df: pd.DataFrame) -> dict:
    from services.governance.entities import default_reporting_entity
    default_entity = default_reporting_entity(session, org_id)
    records, cell_coords = [], {}
    for _, row in df.iterrows():
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
            value_eur = float(row["position_value_eur"])
        except (TypeError, ValueError):
            continue  # a row with an unparsable required field is skipped, not fatal to the whole upload
        safeguards = str(row["minimum_safeguards_status"]).strip().lower() if "minimum_safeguards_status" in df.columns and pd.notna(row.get("minimum_safeguards_status")) else None
        if safeguards and safeguards not in SAFEGUARDS_STATUSES:
            safeguards = None
        cell = h3.latlng_to_cell(lat, lon, 8)
        cell_coords[cell] = (lat, lon)
        records.append({
            "entity_id": str(uuid.uuid4()), "org_id": org_id, "reporting_entity_id": default_entity,
            "entity_name": str(row["holding_name"]), "sector": str(row["sector"]),
            "nace_code": str(row["nace_code"]) if "nace_code" in df.columns and pd.notna(row.get("nace_code")) else None,
            "latitude": lat, "longitude": lon, "h3_cell": cell,
            "region": str(row["region"]) if "region" in df.columns and pd.notna(row.get("region")) else None,
            "country": str(row["country"]) if "country" in df.columns and pd.notna(row.get("country")) else None,
            "primary_value_eur": value_eur,
            "borrower_entity_id": str(row["borrower_entity_id"]) if "borrower_entity_id" in df.columns and pd.notna(row.get("borrower_entity_id")) else None,
            "minimum_safeguards_status": safeguards,
        })
    if not records:
        return {"n_landed": 0, "value_landed": 0.0, "cell_coords": {}, "notes": {}}

    session.execute(text("""
        INSERT INTO portfolio_entities (entity_id, org_id, vertical, entity_name, sector, nace_code,
                                         latitude, longitude, h3_cell, region, country, primary_value_eur,
                                         borrower_entity_id, minimum_safeguards_status, reporting_entity_id)
        VALUES (:entity_id, :org_id, 'assetmgmt', :entity_name, :sector, :nace_code,
                :latitude, :longitude, :h3_cell, :region, :country, :primary_value_eur,
                :borrower_entity_id, :minimum_safeguards_status, CAST(:reporting_entity_id AS uuid))
    """), records)
    return {"n_landed": len(records), "value_landed": float(sum(r["primary_value_eur"] for r in records)),
            "cell_coords": cell_coords, "notes": {}}


def ingest_plots(session: Session, org_id: str, df: pd.DataFrame) -> dict:
    from services.intelligence.geometry import validate_plot_geometry
    from services.reference.iso_country import is_valid_country
    commodity_ids = {row["name"]: str(row["commodity_id"]) for row in
                     session.execute(text("SELECT commodity_id, name FROM sc_commodities")).mappings().all()}
    import json as _json
    has_geo = "plot_geojson" in df.columns
    records, cell_coords, unknown_commodities = [], {}, set()
    geometry_errors, needs_polygon, skipped, invalid_country_codes = [], [], [], []
    for _, row in df.iterrows():
        name = (str(row.get("plot_name")).strip() if pd.notna(row.get("plot_name")) else "") or "(unnamed)"
        try:
            spend = float(row["annual_spend_eur"])
        except (TypeError, ValueError):
            skipped.append({"plot": name, "reason": "missing or unparseable annual_spend_eur"})
            continue
        commodity = str(row["commodity"])
        commodity_id = commodity_ids.get(commodity)
        if not commodity_id:
            unknown_commodities.add(commodity)
            continue

        # Geolocation: a GeoJSON boundary (preferred, EUDR-grade) wins; else the lat/lon point.
        geojson = None
        area_ha = float(row["plot_area_ha"]) if "plot_area_ha" in df.columns and pd.notna(row.get("plot_area_ha")) else None
        lat = lon = None
        if has_geo and pd.notna(row.get("plot_geojson")) and str(row.get("plot_geojson")).strip():
            v = validate_plot_geometry(row["plot_geojson"], declared_area_ha=area_ha)
            if not v["ok"]:
                geometry_errors.append({"plot": name, "error": v["error"]})
                continue
            geojson, lat, lon = _json.dumps(v["geojson"]), v["lat"], v["lon"]
            if v["kind"] == "polygon":
                area_ha = v["area_ha"]
            if v["needs_polygon"]:
                needs_polygon.append(name)  # a >4ha plot still sent as a point — flagged, not blocked
        else:
            try:
                lat, lon = float(row["latitude"]), float(row["longitude"])
            except (TypeError, ValueError):
                skipped.append({"plot": name, "reason": "missing or unparseable coordinates"})
                continue
            # a blank cell parses to NaN — skip it, never let NaN reach h3 (which would 500 the whole upload)
            if lat != lat or lon != lon:
                skipped.append({"plot": name, "reason": "missing or unparseable coordinates"})
                continue
            # A >4ha plot with only a point is EUDR-insufficient — flag it honestly.
            if area_ha is not None and area_ha > 4.0:
                needs_polygon.append(name)

        cell = h3.latlng_to_cell(lat, lon, 8)
        cell_coords[cell] = (lat, lon)
        country = str(row["country"]).strip() if "country" in df.columns and pd.notna(row.get("country")) else None
        if country and not is_valid_country(country):
            invalid_country_codes.append({"plot": name, "country": country})
            country = None   # a bogus ISO code is flagged and dropped, not stored silently
        records.append({
            "plot_id": str(uuid.uuid4()), "org_id": org_id, "commodity_id": commodity_id,
            "plot_name": name, "latitude": lat, "longitude": lon, "h3_cell": cell,
            "region": str(row["region"]) if "region" in df.columns and pd.notna(row.get("region")) else None,
            "country": country,
            "annual_spend_eur": spend, "plot_area_ha": area_ha, "plot_geometry": geojson,
            # bulk upload supplies exact coordinates → exact precision, full confidence (audit T4b)
            "confidence": 1.0, "geocode_precision": "exact",
            "irrigation_status": _norm_irrigation(row.get("irrigation_status")) if "irrigation_status" in df.columns else None,
        })
    if not records:
        return {"n_landed": 0, "value_landed": 0.0, "cell_coords": {}, "notes": {"unknown_commodities": sorted(unknown_commodities), "geometry_errors": geometry_errors, "needs_polygon": needs_polygon, "skipped": skipped, "invalid_country_codes": invalid_country_codes}}

    session.execute(text("""
        INSERT INTO sc_sourcing_plots (plot_id, org_id, commodity_id, plot_name, latitude, longitude,
                                        h3_cell, region, country, annual_spend_eur, plot_area_ha, plot_geometry,
                                        confidence, geocode_precision, irrigation_status)
        VALUES (:plot_id, :org_id, :commodity_id, :plot_name, :latitude, :longitude,
                :h3_cell, :region, :country, :annual_spend_eur, :plot_area_ha, CAST(:plot_geometry AS jsonb),
                :confidence, :geocode_precision, :irrigation_status)
    """), records)
    return {"n_landed": len(records), "value_landed": float(sum(r["annual_spend_eur"] for r in records)),
            "cell_coords": cell_coords,
            "notes": {"unknown_commodities": sorted(unknown_commodities), "geometry_errors": geometry_errors,
                      "needs_polygon": needs_polygon, "skipped": skipped, "invalid_country_codes": invalid_country_codes}}
