"""Each sector's book, as the intake pipeline sees it: how a checked row becomes an asset record, what the live book
already holds, and how a record is inserted (new asset) or applied to an existing asset (update).

Split on purpose (2026-09-25, intake phase 2):
  * build()  runs at CHECK time, before any approval. Everything the engine needs is resolved here — a valuation,
             a known commodity, a valid geometry, plausible values. A row that cannot become an asset is a
             REJECTED ROW with a reason at check time, never a row silently dropped at landing.
  * existing() gives the live book in the same record shape, so matching can compare field by field.
  * insert() / update() only write; they never decide. Updates change the facts the customer owns (principle 1:
    client wins on facts about their own assets); Tellumen-derived fields (scores, EUDR determination,
    taxonomy status) are never written from a file, and a stale derived result is cleared when its input moved.
Values are built at the precision the book stores them (money to the cent), so a re-sent file compares equal.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Callable

import h3
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.ingest.sector_contract import (  # noqa: F401 — RowIssue/Sector are re-exported for callers
    _GOVT_LEVELS,
    RowIssue,
    Sector,
    _f,
    _i,
    _location,
    _m,
    _plausible_building,
    _positive,
    _s,
    _vocab,
)
from services.ingest.templates import (
    CONSTRUCTION_TYPES,
    EPC_RATINGS,
    IRRIGATION_VALUES,
    SAFEGUARDS_STATUSES,
)


def _default_entity(session: Session, org_id: str) -> dict:
    from services.governance.entities import default_reporting_entity
    return {"default_entity": default_reporting_entity(session, org_id)}


def _pe_existing(vertical: str, extra_select: str = "", extra_join: str = "") -> Callable[[Session, str], list[dict]]:
    def load(session: Session, org_id: str) -> list[dict]:
        rows = session.execute(text(f"""
            SELECT e.entity_id::text AS entity_id, e.external_ref, e.entity_name, e.entity_type, e.latitude, e.longitude, e.h3_cell,
                   e.region, e.country, CAST(e.primary_value_eur AS FLOAT) AS primary_value_eur, e.sector, e.nace_code,
                   e.construction_type, e.year_built, e.number_of_stories, e.borrower_entity_id, e.minimum_safeguards_status
                   {extra_select}
            FROM portfolio_entities e {extra_join}
            WHERE e.org_id = CAST(:o AS uuid) AND e.vertical = :v AND e.source = 'own'
        """), {"o": org_id, "v": vertical}).mappings().all()
        return [dict(r) for r in rows]
    return load


def _pe_update(session: Session, records: list[dict], fields: tuple[str, ...]) -> None:
    sets = ", ".join(f"{f} = :{f}" for f in fields)
    session.execute(text(f"UPDATE portfolio_entities SET {sets}, updated_at = now() WHERE entity_id = CAST(:entity_id AS uuid) AND org_id = CAST(:org_id AS uuid)"),
                    records)


_PE_COMMON = ("entity_name", "latitude", "longitude", "h3_cell", "region", "country", "primary_value_eur", "external_ref")


# ── bank: loan tape → portfolio_entities (banking) + ext_banking ──

def _bank_build(ctx: dict, row: dict) -> dict:
    lat, lon, cell = _location(row)
    name, atype, sector = _s(row, "asset_name"), _s(row, "asset_type"), _s(row, "sector")
    if not (name and atype and sector):
        raise RowIssue("asset_name, asset_type and sector are required")
    evic = _positive(row, "counterparty_evic_eur", "counterparty_evic_eur")
    origination = _s(row, "loan_origination_date")
    return {"entity_name": name, "entity_type": atype, "latitude": lat, "longitude": lon, "h3_cell": cell,
            "region": _s(row, "region"), "country": _s(row, "country"),
            "primary_value_eur": _positive(row, "appraised_value_eur", "appraised_value_eur"), "sector": sector,
            "borrower_entity_id": _s(row, "borrower_entity_id"),
            "minimum_safeguards_status": _vocab(row, "minimum_safeguards_status", SAFEGUARDS_STATUSES),
            "external_ref": _s(row, "external_ref"),
            "outstanding_loan_balance_eur": _m(row, "outstanding_loan_balance_eur"),
            "loan_origination_date": origination[:10] if origination else None,
            "counterparty_evic_eur": evic,
            "counterparty_govt_level": _vocab(row, "counterparty_govt_level", _GOVT_LEVELS)}


def _bank_insert(session: Session, org_id: str, ctx: dict, recs: list[dict]) -> None:
    for r in recs:
        r.setdefault("entity_id", str(uuid.uuid4()))
        r["org_id"], r["reporting_entity_id"] = org_id, ctx.get("default_entity")
    session.execute(text("""
        INSERT INTO portfolio_entities (entity_id, org_id, vertical, entity_name, entity_type, latitude, longitude, h3_cell,
                                        region, country, primary_value_eur, sector, borrower_entity_id, minimum_safeguards_status,
                                        reporting_entity_id, external_ref)
        VALUES (CAST(:entity_id AS uuid), CAST(:org_id AS uuid), 'banking', :entity_name, :entity_type, :latitude, :longitude, :h3_cell,
                :region, :country, :primary_value_eur, :sector, :borrower_entity_id, :minimum_safeguards_status,
                CAST(:reporting_entity_id AS uuid), :external_ref)
    """), recs)
    session.execute(text("""
        INSERT INTO ext_banking (entity_id, outstanding_loan_balance_eur, loan_origination_date, taxonomy_status,
                                 counterparty_evic_eur, counterparty_govt_level)
        VALUES (CAST(:entity_id AS uuid), :outstanding_loan_balance_eur, CAST(:loan_origination_date AS date), 'not_assessed',
                :counterparty_evic_eur, :counterparty_govt_level)
    """), recs)


def _bank_update(session: Session, org_id: str, ctx: dict, recs: list[dict]) -> None:
    for r in recs:
        r["org_id"] = org_id
    _pe_update(session, recs, _PE_COMMON + ("entity_type", "sector", "borrower_entity_id", "minimum_safeguards_status"))
    session.execute(text("""
        UPDATE ext_banking SET outstanding_loan_balance_eur = :outstanding_loan_balance_eur,
               loan_origination_date = CAST(:loan_origination_date AS date), counterparty_evic_eur = :counterparty_evic_eur,
               counterparty_govt_level = :counterparty_govt_level
        WHERE entity_id = CAST(:entity_id AS uuid)
    """), recs)


BANK = Sector("bank_assets", "entity_name", "primary_value_eur",
              _PE_COMMON + ("entity_type", "sector", "borrower_entity_id", "minimum_safeguards_status",
                            "outstanding_loan_balance_eur", "loan_origination_date", "counterparty_evic_eur", "counterparty_govt_level"),
              _default_entity, _bank_build,
              _pe_existing("banking", """, CAST(x.outstanding_loan_balance_eur AS FLOAT) AS outstanding_loan_balance_eur,
                           to_char(x.loan_origination_date, 'YYYY-MM-DD') AS loan_origination_date,
                           CAST(x.counterparty_evic_eur AS FLOAT) AS counterparty_evic_eur, x.counterparty_govt_level""",
                           "LEFT JOIN ext_banking x ON x.entity_id = e.entity_id"),
              _bank_insert, _bank_update)


# ── insurance: Statement of Values → portfolio_entities (insurance) + ext_insurance ──

def _ins_build(ctx: dict, row: dict) -> dict:
    lat, lon, cell = _location(row)
    name = _s(row, "policy_name")
    if not name:
        raise RowIssue("policy_name is required")
    b, c, bi = _m(row, "building_value_eur"), _m(row, "contents_value_eur"), _m(row, "business_interruption_value_eur")
    if b is not None or c is not None or bi is not None:
        tiv = round((b or 0) + (c or 0) + (bi or 0), 2)
    else:
        tiv = _m(row, "sum_insured_eur")
    if tiv is None:
        raise RowIssue("no valuation: give sum_insured_eur or at least one value component")
    if tiv <= 0:
        raise RowIssue("total insured value must be greater than zero")
    ded = _m(row, "deductible_pct", 4)
    if ded is not None and not (0 <= ded <= 1):
        raise RowIssue(f"deductible_pct {ded} must be a fraction between 0 and 1 (0.02 = 2%)")
    rec = {"entity_name": name, "entity_type": _s(row, "policy_type"), "latitude": lat, "longitude": lon,
           "h3_cell": cell, "region": _s(row, "region"), "country": _s(row, "country"), "primary_value_eur": tiv,
           "construction_type": _vocab(row, "construction_type", CONSTRUCTION_TYPES), "year_built": _i(row, "year_built"),
           "number_of_stories": _i(row, "number_of_stories"), "external_ref": _s(row, "external_ref"),
           "deductible_pct": ded, "building_value_eur": b, "contents_value_eur": c,
           "business_interruption_value_eur": bi, "cresta_zone": _i(row, "cresta_zone"),
           "motor_sum_insured_eur": _m(row, "motor_sum_insured_eur")}
    _plausible_building(rec)
    return rec


def _ins_insert(session: Session, org_id: str, ctx: dict, recs: list[dict]) -> None:
    for r in recs:
        r.setdefault("entity_id", str(uuid.uuid4()))
        r["entity_type"] = r.get("entity_type") or "property"
        r["deductible_pct"] = 0.02 if r.get("deductible_pct") is None else r["deductible_pct"]   # new asset only
        r["org_id"], r["reporting_entity_id"] = org_id, ctx.get("default_entity")
    session.execute(text("""
        INSERT INTO portfolio_entities (entity_id, org_id, vertical, entity_name, entity_type, latitude, longitude, h3_cell,
                                        region, country, primary_value_eur, construction_type, year_built, number_of_stories,
                                        reporting_entity_id, external_ref)
        VALUES (CAST(:entity_id AS uuid), CAST(:org_id AS uuid), 'insurance', :entity_name, :entity_type, :latitude, :longitude, :h3_cell,
                :region, :country, :primary_value_eur, :construction_type, :year_built, :number_of_stories,
                CAST(:reporting_entity_id AS uuid), :external_ref)
    """), recs)
    session.execute(text("""
        INSERT INTO ext_insurance (entity_id, deductible_pct, building_value_eur, contents_value_eur,
                                   business_interruption_value_eur, cresta_zone, motor_sum_insured_eur)
        VALUES (CAST(:entity_id AS uuid), :deductible_pct, :building_value_eur, :contents_value_eur,
                :business_interruption_value_eur, :cresta_zone, :motor_sum_insured_eur)
    """), recs)


def _ins_update(session: Session, org_id: str, ctx: dict, recs: list[dict]) -> None:
    for r in recs:
        r["org_id"] = org_id
    _pe_update(session, recs, _PE_COMMON + ("entity_type", "construction_type", "year_built", "number_of_stories"))
    session.execute(text("""
        UPDATE ext_insurance SET deductible_pct = :deductible_pct, building_value_eur = :building_value_eur,
               contents_value_eur = :contents_value_eur, business_interruption_value_eur = :business_interruption_value_eur,
               cresta_zone = :cresta_zone, motor_sum_insured_eur = :motor_sum_insured_eur
        WHERE entity_id = CAST(:entity_id AS uuid)
    """), recs)


INSURANCE = Sector("insurance_policies", "entity_name", "primary_value_eur",
                   _PE_COMMON + ("entity_type", "construction_type", "year_built", "number_of_stories", "deductible_pct",
                                 "building_value_eur", "contents_value_eur", "business_interruption_value_eur",
                                 "cresta_zone", "motor_sum_insured_eur"),
                   _default_entity, _ins_build,
                   _pe_existing("insurance", """, CAST(x.deductible_pct AS FLOAT) AS deductible_pct,
                                CAST(x.building_value_eur AS FLOAT) AS building_value_eur, CAST(x.contents_value_eur AS FLOAT) AS contents_value_eur,
                                CAST(x.business_interruption_value_eur AS FLOAT) AS business_interruption_value_eur, x.cresta_zone,
                                CAST(x.motor_sum_insured_eur AS FLOAT) AS motor_sum_insured_eur""",
                                "LEFT JOIN ext_insurance x ON x.entity_id = e.entity_id"),
                   _ins_insert, _ins_update)


# ── real estate: property schedule → portfolio_entities (realestate) + ext_realestate ──

def _rei_build(ctx: dict, row: dict) -> dict:
    lat, lon, cell = _location(row)
    name, ptype = _s(row, "property_name"), _s(row, "property_type")
    if not (name and ptype):
        raise RowIssue("property_name and property_type are required")
    noi = _m(row, "annual_noi_eur")
    if noi is None:
        raise RowIssue("annual_noi_eur is missing")
    rec = {"entity_name": name, "entity_type": ptype, "latitude": lat, "longitude": lon, "h3_cell": cell,
           "region": _s(row, "region"), "country": _s(row, "country"),
           "primary_value_eur": _positive(row, "property_value_eur", "property_value_eur"), "annual_noi_eur": noi,
           "annual_gross_rental_revenue_eur": _m(row, "annual_gross_rental_revenue_eur"),
           "construction_type": _vocab(row, "construction_type", CONSTRUCTION_TYPES), "year_built": _i(row, "year_built"),
           "number_of_stories": _i(row, "number_of_stories"), "epc_rating": _vocab(row, "epc_rating", EPC_RATINGS, upper=True),
           "borrower_entity_id": _s(row, "borrower_entity_id"),
           "minimum_safeguards_status": _vocab(row, "minimum_safeguards_status", SAFEGUARDS_STATUSES),
           "external_ref": _s(row, "external_ref")}
    _plausible_building(rec)
    return rec


def _rei_insert(session: Session, org_id: str, ctx: dict, recs: list[dict]) -> None:
    for r in recs:
        r.setdefault("entity_id", str(uuid.uuid4()))
        r["org_id"], r["reporting_entity_id"] = org_id, ctx.get("default_entity")
    session.execute(text("""
        INSERT INTO portfolio_entities (entity_id, org_id, vertical, entity_name, entity_type, latitude, longitude, h3_cell,
                                        region, country, primary_value_eur, construction_type, year_built, number_of_stories,
                                        borrower_entity_id, minimum_safeguards_status, reporting_entity_id, external_ref)
        VALUES (CAST(:entity_id AS uuid), CAST(:org_id AS uuid), 'realestate', :entity_name, :entity_type, :latitude, :longitude, :h3_cell,
                :region, :country, :primary_value_eur, :construction_type, :year_built, :number_of_stories,
                :borrower_entity_id, :minimum_safeguards_status, CAST(:reporting_entity_id AS uuid), :external_ref)
    """), recs)
    session.execute(text("""
        INSERT INTO ext_realestate (entity_id, annual_noi_eur, epc_rating, annual_gross_rental_revenue_eur)
        VALUES (CAST(:entity_id AS uuid), :annual_noi_eur, :epc_rating, :annual_gross_rental_revenue_eur)
    """), recs)


def _rei_update(session: Session, org_id: str, ctx: dict, recs: list[dict]) -> None:
    for r in recs:
        r["org_id"] = org_id
    _pe_update(session, recs, _PE_COMMON + ("entity_type", "construction_type", "year_built", "number_of_stories",
                                            "borrower_entity_id", "minimum_safeguards_status"))
    session.execute(text("""
        UPDATE ext_realestate SET annual_noi_eur = :annual_noi_eur, epc_rating = :epc_rating,
               annual_gross_rental_revenue_eur = :annual_gross_rental_revenue_eur
        WHERE entity_id = CAST(:entity_id AS uuid)
    """), recs)


REALESTATE = Sector("realestate_properties", "entity_name", "primary_value_eur",
                    _PE_COMMON + ("entity_type", "construction_type", "year_built", "number_of_stories", "borrower_entity_id",
                                  "minimum_safeguards_status", "annual_noi_eur", "epc_rating", "annual_gross_rental_revenue_eur"),
                    _default_entity, _rei_build,
                    _pe_existing("realestate", """, CAST(x.annual_noi_eur AS FLOAT) AS annual_noi_eur, x.epc_rating,
                                 CAST(x.annual_gross_rental_revenue_eur AS FLOAT) AS annual_gross_rental_revenue_eur""",
                                 "LEFT JOIN ext_realestate x ON x.entity_id = e.entity_id"),
                    _rei_insert, _rei_update)


# ── asset management: holdings book → portfolio_entities (assetmgmt) ──

def _hol_build(ctx: dict, row: dict) -> dict:
    lat, lon, cell = _location(row)
    name, sector = _s(row, "holding_name"), _s(row, "sector")
    if not (name and sector):
        raise RowIssue("holding_name and sector are required")
    return {"entity_name": name, "sector": sector, "nace_code": _s(row, "nace_code"), "latitude": lat, "longitude": lon,
            "h3_cell": cell, "region": _s(row, "region"), "country": _s(row, "country"),
            "primary_value_eur": _positive(row, "position_value_eur", "position_value_eur"),
            "borrower_entity_id": _s(row, "borrower_entity_id"),
            "minimum_safeguards_status": _vocab(row, "minimum_safeguards_status", SAFEGUARDS_STATUSES),
            "external_ref": _s(row, "external_ref")}


def _hol_insert(session: Session, org_id: str, ctx: dict, recs: list[dict]) -> None:
    for r in recs:
        r.setdefault("entity_id", str(uuid.uuid4()))
        r["org_id"], r["reporting_entity_id"] = org_id, ctx.get("default_entity")
    session.execute(text("""
        INSERT INTO portfolio_entities (entity_id, org_id, vertical, entity_name, sector, nace_code, latitude, longitude, h3_cell,
                                        region, country, primary_value_eur, borrower_entity_id, minimum_safeguards_status,
                                        reporting_entity_id, external_ref)
        VALUES (CAST(:entity_id AS uuid), CAST(:org_id AS uuid), 'assetmgmt', :entity_name, :sector, :nace_code, :latitude, :longitude,
                :h3_cell, :region, :country, :primary_value_eur, :borrower_entity_id, :minimum_safeguards_status,
                CAST(:reporting_entity_id AS uuid), :external_ref)
    """), recs)


def _hol_update(session: Session, org_id: str, ctx: dict, recs: list[dict]) -> None:
    for r in recs:
        r["org_id"] = org_id
    _pe_update(session, recs, _PE_COMMON + ("sector", "nace_code", "borrower_entity_id", "minimum_safeguards_status"))


HOLDINGS = Sector("assetmgmt_holdings", "entity_name", "primary_value_eur",
                  _PE_COMMON + ("sector", "nace_code", "borrower_entity_id", "minimum_safeguards_status"),
                  _default_entity, _hol_build, _pe_existing("assetmgmt"), _hol_insert, _hol_update)


# ── agriculture: sourcing plots → sc_sourcing_plots ──

def _plot_prepare(session: Session, org_id: str) -> dict:
    return {"commodity_ids": {r["name"]: str(r["commodity_id"]) for r in
                              session.execute(text("SELECT commodity_id, name FROM sc_commodities")).mappings().all()}}


def _plot_build(ctx: dict, row: dict) -> dict:
    from services.intelligence.geometry import validate_plot_geometry
    from services.reference.iso_country import is_valid_country
    name = _s(row, "plot_name")
    if not name:
        raise RowIssue("plot_name is required")
    spend = _positive(row, "annual_spend_eur", "annual_spend_eur")
    commodity = _s(row, "commodity")
    cid = ctx["commodity_ids"].get(commodity or "")
    if not cid:
        raise RowIssue(f"commodity '{commodity}' is not on this platform")
    area = _m(row, "plot_area_ha")
    geo = _s(row, "plot_geojson")
    needs_polygon = False
    if geo:
        v = validate_plot_geometry(geo, declared_area_ha=area)
        if not v["ok"]:
            raise RowIssue(f"plot boundary is invalid: {v['error']}")
        geojson, lat, lon = json.dumps(v["geojson"], sort_keys=True), v["lat"], v["lon"]
        if v["kind"] == "polygon":
            area = round(v["area_ha"], 2)
        needs_polygon = bool(v["needs_polygon"])
        cell = h3.latlng_to_cell(lat, lon, 8)
    else:
        geojson = None
        lat, lon, cell = _location(row)
        needs_polygon = area is not None and area > 4.0
    country = _s(row, "country")
    if country and not is_valid_country(country):
        raise RowIssue(f"country '{country}' is not a valid ISO-2 code")
    return {"plot_name": name, "commodity_id": cid, "latitude": lat, "longitude": lon, "h3_cell": cell,
            "region": _s(row, "region"), "country": country.upper() if country else None, "annual_spend_eur": spend,
            "plot_area_ha": area, "plot_geometry": geojson, "irrigation_status": _vocab(row, "irrigation_status", IRRIGATION_VALUES),
            "external_ref": _s(row, "external_ref"), "_needs_polygon": needs_polygon}


def _plot_existing(session: Session, org_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT plot_id::text AS entity_id, external_ref, plot_name, commodity_id::text AS commodity_id, latitude, longitude, h3_cell,
               region, country, CAST(annual_spend_eur AS FLOAT) AS annual_spend_eur, CAST(plot_area_ha AS FLOAT) AS plot_area_ha,
               plot_geometry::text AS plot_geometry, irrigation_status
        FROM sc_sourcing_plots WHERE org_id = CAST(:o AS uuid) AND source = 'own'
    """), {"o": org_id}).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        if d["plot_geometry"]:   # canonical JSON so an unchanged boundary compares equal
            d["plot_geometry"] = json.dumps(json.loads(d["plot_geometry"]), sort_keys=True)
        out.append(d)
    return out


def _plot_insert(session: Session, org_id: str, ctx: dict, recs: list[dict]) -> None:
    for r in recs:
        r.setdefault("entity_id", str(uuid.uuid4()))
        r["org_id"] = org_id
    session.execute(text("""
        INSERT INTO sc_sourcing_plots (plot_id, org_id, commodity_id, plot_name, latitude, longitude, h3_cell, region, country,
                                       annual_spend_eur, plot_area_ha, plot_geometry, confidence, geocode_precision,
                                       irrigation_status, external_ref)
        VALUES (CAST(:entity_id AS uuid), CAST(:org_id AS uuid), CAST(:commodity_id AS uuid), :plot_name, :latitude, :longitude,
                :h3_cell, :region, :country, :annual_spend_eur, :plot_area_ha, CAST(:plot_geometry AS jsonb), 1.0, 'exact',
                :irrigation_status, :external_ref)
    """), recs)


def _plot_update(session: Session, org_id: str, ctx: dict, recs: list[dict]) -> None:
    for r in recs:
        r["org_id"] = org_id
    # a moved plot or changed boundary makes the satellite EUDR determination stale: clear it, never keep a result for
    # a location it was not computed on (re-run /eudr/determine to refresh)
    session.execute(text("""
        UPDATE sc_sourcing_plots p SET
               eudr_determination = CASE WHEN p.latitude IS DISTINCT FROM :latitude OR p.longitude IS DISTINCT FROM :longitude
                                          OR p.plot_geometry IS DISTINCT FROM CAST(:plot_geometry AS jsonb) THEN NULL ELSE p.eudr_determination END,
               eudr_determined_at = CASE WHEN p.latitude IS DISTINCT FROM :latitude OR p.longitude IS DISTINCT FROM :longitude
                                          OR p.plot_geometry IS DISTINCT FROM CAST(:plot_geometry AS jsonb) THEN NULL ELSE p.eudr_determined_at END,
               commodity_id = CAST(:commodity_id AS uuid), plot_name = :plot_name, latitude = :latitude, longitude = :longitude,
               h3_cell = :h3_cell, region = :region, country = :country, annual_spend_eur = :annual_spend_eur,
               plot_area_ha = :plot_area_ha, plot_geometry = CAST(:plot_geometry AS jsonb), irrigation_status = :irrigation_status,
               external_ref = :external_ref
        WHERE p.plot_id = CAST(:entity_id AS uuid) AND p.org_id = CAST(:org_id AS uuid)
    """), recs)


PLOTS = Sector("supply_plots", "plot_name", "annual_spend_eur",
               ("plot_name", "commodity_id", "latitude", "longitude", "region", "country", "annual_spend_eur", "plot_area_ha",
                "plot_geometry", "irrigation_status", "external_ref"),
               _plot_prepare, _plot_build, _plot_existing, _plot_insert, _plot_update)


SECTORS: dict[str, Sector] = {s.key: s for s in (BANK, INSURANCE, REALESTATE, HOLDINGS, PLOTS)}


def write(session: Session, sector: Sector, org_id: str, ctx: dict, new: list[dict], updates: list[dict]) -> dict:
    """Write already-decided records. Returns the cells whose location is new or changed, for scoring."""
    def clean(r: dict) -> dict:
        return {k: v for k, v in r.items() if not k.startswith("_")}
    new_c, upd_c = [clean(r) for r in new], [clean(r) for r in updates]
    if new_c:
        sector.insert(session, org_id, ctx, new_c)
    if upd_c:
        sector.update(session, org_id, ctx, upd_c)
    cells: dict[str, Any] = {}
    for r in new + [u for u in updates if u.get("_moved")]:
        cells[r["h3_cell"]] = (r["latitude"], r["longitude"])
    return {"cell_coords": cells, "entity_ids": [r["entity_id"] for r in new_c]}
