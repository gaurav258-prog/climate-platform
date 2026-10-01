"""EUDR books for the governed intake (Regulation (EU) 2023/1115; E92): the parties a placing or export names (Art. 5(3),
9(1)(e)-(f)), each placing on the market, making available or export (Annex II points 1-3, Art. 9(1)(a)-(c)), and the
plots each came from with the date range of production (Art. 9(1)(d)).

A row either becomes a record or is refused with a message the undertaking can act on; nothing is guessed. A movement in
a statement under review or filed is not changed by a file (the database refuses it too, eudr_foundation_20261001).
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.ingest.sector_contract import (
    RowIssue,
    Sector,
    _f,
    _i,
    _s,
    _vocab,
    group_entity_fields,
)

_EDITABLE = ("draft", "returned", "withdrawn", "superseded")    # statuses of its statement in which a movement may change


def _date(row: dict, k: str, label: str, required: bool = True) -> str | None:
    v = _s(row, k)
    if v is None:
        if required:
            raise RowIssue(f"{label} is missing")
        return None
    try:
        return date.fromisoformat(v[:10]).isoformat()
    except ValueError:
        raise RowIssue(f"{label} '{v}' is not a date (YYYY-MM-DD)")


def _list(row: dict, k: str) -> list[str] | None:
    v = _s(row, k)
    return [x.strip() for x in v.split(";") if x.strip()] or None if v else None


# ── suppliers / customers → sc_suppliers / sc_customers ──

def _party(table: str, id_col: str, key: str, label: str) -> Sector:
    def prepare(session: Session, org_id: str) -> dict:
        return {}

    def build(ctx: dict, row: dict) -> dict:
        from services.reference.iso_country import is_valid_country
        name, ref = _s(row, "party_name"), _s(row, "party_ref")
        if not name or not ref:
            raise RowIssue(f"the {label}'s name and your id for it are required")
        email = _s(row, "contact_email")
        if not email or "@" not in email:
            raise RowIssue("an email address is required (Art. 9(1)(e)-(f))")
        address = _s(row, "address")
        if not address:
            raise RowIssue("the postal address is required (Art. 9(1)(e)-(f))")
        country = _s(row, "country")
        if country and not is_valid_country(country):
            raise RowIssue(f"country '{country}' is not a valid ISO-2 code")
        return {"party_name": name, "external_ref": ref, "address": address, "contact_email": email,
                "trade_name": _s(row, "trade_name"), "web_address": _s(row, "web_address"),
                "country": country.upper() if country else None, "latitude": None, "longitude": None}

    def existing(session: Session, org_id: str) -> list[dict]:
        return [dict(r) for r in session.execute(text(f"""
            SELECT {id_col}::text AS entity_id, external_ref, name AS party_name, address, contact_email, trade_name,
                   web_address, country, NULL::float AS latitude, NULL::float AS longitude
            FROM {table} WHERE org_id = CAST(:o AS uuid)"""), {"o": org_id}).mappings().all()]

    def insert(session: Session, org_id: str, ctx: dict, recs: list[dict]) -> None:
        for r in recs:
            r.setdefault("entity_id", str(uuid.uuid4()))
            r["org_id"] = org_id
        session.execute(text(f"""
            INSERT INTO {table} ({id_col}, org_id, name, address, contact_email, trade_name, web_address, country, external_ref)
            VALUES (CAST(:entity_id AS uuid), CAST(:org_id AS uuid), :party_name, :address, :contact_email, :trade_name,
                    :web_address, :country, :external_ref)"""), recs)

    def update(session: Session, org_id: str, ctx: dict, recs: list[dict]) -> None:
        for r in recs:
            r["org_id"] = org_id
        session.execute(text(f"""
            UPDATE {table} SET name = :party_name, address = :address, contact_email = :contact_email,
                   trade_name = :trade_name, web_address = :web_address, country = :country, external_ref = :external_ref
            WHERE {id_col} = CAST(:entity_id AS uuid) AND org_id = CAST(:org_id AS uuid)"""), recs)

    return Sector(key, "party_name", "_no_value",
                  ("party_name", "address", "contact_email", "trade_name", "web_address", "country"),
                  prepare, build, existing, insert, update, table=table, id_column=id_col, asset_book=False)


SUPPLIERS = _party("sc_suppliers", "supplier_id", "eudr_suppliers", "supplier")
CUSTOMERS = _party("sc_customers", "customer_id", "eudr_customers", "customer")


# ── placings / making available / exports → eudr_movement ──

def _refs(session: Session, table: str, id_col: str, org_id: str) -> dict:
    return {r[0]: str(r[1]) for r in session.execute(text(
        f"SELECT external_ref, {id_col} FROM {table} WHERE org_id = CAST(:o AS uuid) AND external_ref IS NOT NULL"),
        {"o": org_id}).all()}


def _frozen_movements(session: Session, org_id: str) -> set[str]:
    return {str(r[0]) for r in session.execute(text("""
        SELECT eudr_movement_id FROM regulatory_filing WHERE org_id = CAST(:o AS uuid) AND eudr_movement_id IS NOT NULL
          AND status <> ALL(CAST(:ok AS text[]))"""), {"o": org_id, "ok": list(_EDITABLE)}).all()}


def _mv_prepare(session: Session, org_id: str) -> dict:
    from services.ingest.sector_ingest import _default_entity
    return {**_default_entity(session, org_id), "suppliers": _refs(session, "sc_suppliers", "supplier_id", org_id),
            "customers": _refs(session, "sc_customers", "customer_id", org_id),
            "frozen_refs": {r[0] for r in session.execute(text("""
                SELECT m.external_ref FROM eudr_movement m WHERE m.org_id = CAST(:o AS uuid)
                  AND m.movement_id::text = ANY(CAST(:f AS text[]))"""), {"o": org_id, "f": list(_frozen_movements(session, org_id))}).all()}}


def _mv_build(ctx: dict, row: dict) -> dict:
    import re
    ref = _s(row, "movement_ref")
    if not ref:
        raise RowIssue("your shipment id is required")
    if ref in ctx["frozen_refs"]:
        raise RowIssue(f"shipment '{ref}' is in a due diligence statement under review or filed — it cannot be changed by a "
                       "file (withdraw or amend the statement)")
    kind = _vocab(row, "movement_kind", "eudr_movement")
    role = _vocab(row, "actor_role", "eudr_role")
    if not kind or not role:
        raise RowIssue("say whether it is a placing, making_available or export, and your role in it")
    hs = (_s(row, "hs_code") or "").replace(" ", "").replace(".", "")
    if not re.fullmatch(r"[0-9]{4}([0-9]{2}){0,3}", hs):
        raise RowIssue(f"HS code '{_s(row, 'hs_code')}' is not 4, 6, 8 or 10 digits")
    desc = _s(row, "description")
    if not desc:
        raise RowIssue("a description of the product is required (Annex II point 2)")
    cf = _vocab(row, "customs_flow", "boolean")
    if cf is None:
        raise RowIssue("say whether the goods pass customs (true / false)")
    customs = cf == "true"
    kg, dev, sq = _f(row, "net_mass_kg"), _f(row, "mass_deviation_pct"), _f(row, "supplementary_qty")
    vol, items, su = _f(row, "volume_m3"), _i(row, "items_count"), _s(row, "supplementary_unit")
    if customs and kg is None:
        raise RowIssue("goods passing customs are stated in kilograms of net mass (Annex II point 2)")
    if kg is None and vol is None and items is None:
        raise RowIssue("give the quantity: net mass, or where applicable volume or number of items")
    if (su is None) != (sq is None):
        raise RowIssue("a supplementary unit comes with its quantity")
    sup, cus = _s(row, "supplier_ref"), _s(row, "customer_ref")
    if sup and sup not in ctx["suppliers"]:
        raise RowIssue(f"supplier '{sup}' is not in your suppliers (send the suppliers file first)")
    if cus and cus not in ctx["customers"]:
        raise RowIssue(f"customer '{cus}' is not in your customers (send the customers file first)")
    return {"movement_ref": ref, "external_ref": ref, "kind": kind, "actor_role": role,
            "planned_on": _date(row, "planned_on", "the date"), "hs_code": hs, "description": desc,
            "trade_name": _s(row, "trade_name"), "scientific_names": _list(row, "scientific_names"), "customs_flow": customs,
            "net_mass_kg": kg, "mass_deviation_pct": dev, "supplementary_unit": su, "supplementary_qty": sq,
            "volume_m3": vol, "items_count": items, "supplier_id": ctx["suppliers"].get(sup) if sup else None,
            "customer_id": ctx["customers"].get(cus) if cus else None, "upstream_refs": _list(row, "upstream_refs"),
            "latitude": None, "longitude": None, **group_entity_fields(ctx, row)}


_MV_COLS = ("kind", "actor_role", "planned_on", "hs_code", "description", "trade_name", "scientific_names", "customs_flow",
            "net_mass_kg", "mass_deviation_pct", "supplementary_unit", "supplementary_qty", "volume_m3", "items_count",
            "supplier_id", "customer_id", "upstream_refs")


def _mv_existing(session: Session, org_id: str) -> list[dict]:
    rows = session.execute(text(f"""
        SELECT movement_id::text AS entity_id, external_ref, external_ref AS movement_ref, {", ".join(_MV_COLS)},
               reporting_entity_id::text AS reporting_entity_id, NULL::float AS latitude, NULL::float AS longitude
        FROM eudr_movement WHERE org_id = CAST(:o AS uuid)"""), {"o": org_id}).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        d["planned_on"] = d["planned_on"].isoformat()
        for k in ("net_mass_kg", "mass_deviation_pct", "supplementary_qty", "volume_m3"):
            d[k] = float(d[k]) if d[k] is not None else None
        d["supplier_id"] = d["supplier_id"] and str(d["supplier_id"])
        d["customer_id"] = d["customer_id"] and str(d["customer_id"])
        out.append(d)
    return out


def _mv_write(session: Session, org_id: str, ctx: dict, recs: list[dict], new: bool) -> None:
    for r in recs:
        if new:
            r.setdefault("entity_id", str(uuid.uuid4()))
        r["org_id"], r["entity"] = org_id, r.get("reporting_entity_id") or ctx.get("default_entity")
    vals = ", ".join(f":{c}" for c in _MV_COLS).replace(":planned_on", "CAST(:planned_on AS date)") \
        .replace(":supplier_id", "CAST(:supplier_id AS uuid)").replace(":customer_id", "CAST(:customer_id AS uuid)")
    if new:
        session.execute(text(f"""
            INSERT INTO eudr_movement (movement_id, org_id, reporting_entity_id, external_ref, {", ".join(_MV_COLS)})
            VALUES (CAST(:entity_id AS uuid), CAST(:org_id AS uuid), CAST(:entity AS uuid), :external_ref, {vals})"""), recs)
    else:
        sets = ", ".join(f"{c} = {v.strip()}" for c, v in zip(_MV_COLS, vals.split(", ")))
        session.execute(text(f"""
            UPDATE eudr_movement SET {sets}, reporting_entity_id = COALESCE(CAST(:entity AS uuid), reporting_entity_id)
            WHERE movement_id = CAST(:entity_id AS uuid) AND org_id = CAST(:org_id AS uuid)"""), recs)


MOVEMENTS = Sector("eudr_movements", "movement_ref", "net_mass_kg", _MV_COLS, _mv_prepare, _mv_build, _mv_existing,
                   lambda s, o, c, r: _mv_write(s, o, c, r, True), lambda s, o, c, r: _mv_write(s, o, c, r, False),
                   table="eudr_movement", id_column="movement_id", group_entities=True, asset_book=False)


# ── the plots a movement came from → eudr_movement_plot ──

_LINK_NS = uuid.UUID("0e0d7a52-3c1f-4c55-9a3e-2b8f6d4c1a90")


def _link_id(movement_id: str, plot_id: str) -> str:
    return str(uuid.uuid5(_LINK_NS, f"{movement_id}@{plot_id}"))


def _mp_prepare(session: Session, org_id: str) -> dict:
    mv = {r[0]: str(r[1]) for r in session.execute(text(
        "SELECT external_ref, movement_id FROM eudr_movement WHERE org_id = CAST(:o AS uuid) AND external_ref IS NOT NULL"),
        {"o": org_id}).all()}
    plots = {}
    for pid, ref in session.execute(text(
            "SELECT plot_id, external_ref FROM sc_sourcing_plots WHERE org_id = CAST(:o AS uuid)"), {"o": org_id}).all():
        plots[str(pid)] = str(pid)
        if ref:
            plots[ref] = str(pid)
    return {"movements": mv, "plots": plots, "frozen": _frozen_movements(session, org_id)}


def _mp_build(ctx: dict, row: dict) -> dict:
    mref, pref = _s(row, "movement_ref"), _s(row, "plot_ref")
    m, p = ctx["movements"].get(mref or ""), ctx["plots"].get(pref or "")
    if m is None:
        raise RowIssue(f"shipment '{mref}' is not one of your shipments (send the shipments file first)")
    if p is None:
        raise RowIssue(f"plot '{pref}' is not one of your plots")
    if m in ctx["frozen"]:
        raise RowIssue(f"shipment '{mref}' is in a due diligence statement under review or filed — its plots cannot change")
    a, b = _date(row, "production_from", "produced from"), _date(row, "production_to", "produced until")
    if b < a:
        raise RowIssue("produced until is before produced from")
    key = _link_id(m, p)
    return {"external_ref": key, "movement_ref": mref, "movement_id": m, "plot_id": p, "production_from": a,
            "production_to": b, "latitude": None, "longitude": None}


def _mp_existing(session: Session, org_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT l.movement_id::text AS movement_id, l.plot_id::text AS plot_id, l.production_from, l.production_to
        FROM eudr_movement_plot l JOIN eudr_movement m USING (movement_id) WHERE m.org_id = CAST(:o AS uuid)"""),
        {"o": org_id}).mappings().all()
    return [{"entity_id": _link_id(r["movement_id"], r["plot_id"]), "external_ref": _link_id(r["movement_id"], r["plot_id"]),
             "movement_ref": None, "movement_id": r["movement_id"], "plot_id": r["plot_id"],
             "production_from": r["production_from"].isoformat(), "production_to": r["production_to"].isoformat(),
             "latitude": None, "longitude": None} for r in rows]


def _mp_write(session: Session, org_id: str, ctx: dict, recs: list[dict]) -> None:
    for r in recs:
        r["entity_id"] = r.get("entity_id") or r["external_ref"]
    session.execute(text("""
        INSERT INTO eudr_movement_plot (movement_id, plot_id, production_from, production_to)
        VALUES (CAST(:movement_id AS uuid), CAST(:plot_id AS uuid), CAST(:production_from AS date), CAST(:production_to AS date))
        ON CONFLICT (movement_id, plot_id) DO UPDATE SET production_from = EXCLUDED.production_from,
            production_to = EXCLUDED.production_to"""), recs)


MOVEMENT_PLOTS = Sector("eudr_movement_plots", "movement_ref", "_no_value", ("production_from", "production_to"),
                        _mp_prepare, _mp_build, _mp_existing, _mp_write, _mp_write,
                        table="eudr_movement_plot", id_column="movement_id", asset_book=False)

SECTORS = (SUPPLIERS, CUSTOMERS, MOVEMENTS, MOVEMENT_PLOTS)
